import boto3
import pandas as pd
import logging
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_clients(region_name='ap-south-1'):
    """Initialize and return AWS clients."""
    try:
        identitystore = boto3.client('identitystore', region_name=region_name)
        sso_admin = boto3.client('sso-admin', region_name=region_name)
        orgs = boto3.client('organizations', region_name=region_name)
        return identitystore, sso_admin, orgs
    except Exception as e:
        logger.error(f"Failed to create boto3 clients: {e}")
        raise

def get_sso_instance(sso_admin_client):
    """Retrieve the SSO Instance ARN and Identity Store ID."""
    try:
        response = sso_admin_client.list_instances()
        if not response['Instances']:
            raise Exception("No SSO Instances found.")
        # Assuming the first instance is the one we want
        instance = response['Instances'][0]
        return instance['InstanceArn'], instance['IdentityStoreId']
    except ClientError as e:
        logger.error(f"Error fetching SSO instance: {e}")
        raise

def list_all_users(identitystore_client, identity_store_id):
    """Fetch all users from Identity Store."""
    users = {}
    paginator = identitystore_client.get_paginator('list_users')
    try:
        for page in paginator.paginate(IdentityStoreId=identity_store_id):
            for user in page['Users']:
                users[user['UserId']] = {
                    'UserName': user.get('UserName'),
                    'DisplayName': user.get('DisplayName'),
                    'Email': user['Emails'][0]['Value'] if user.get('Emails') else 'N/A',
                    'Active': True # Identity Store doesn't always expose efficient active/inactive in list, assuming active if listed or need specific attr
                }
        logger.info(f"Fetched {len(users)} users.")
        return users
    except ClientError as e:
        logger.error(f"Error listing users: {e}")
        raise

def list_all_groups(identitystore_client, identity_store_id):
    """Fetch all groups from Identity Store."""
    groups = {}
    paginator = identitystore_client.get_paginator('list_groups')
    try:
        for page in paginator.paginate(IdentityStoreId=identity_store_id):
            for group in page['Groups']:
                groups[group['GroupId']] = {
                    'Name': group['DisplayName'],
                    'Description': group.get('Description', 'N/A')
                }
        logger.info(f"Fetched {len(groups)} groups.")
        return groups
    except ClientError as e:
        logger.error(f"Error listing groups: {e}")
        raise

def list_group_memberships(identitystore_client, identity_store_id, groups):
    """Map Group IDs to a list of User IDs."""
    group_members = {} # GroupID -> [UserID, UserID, ...]
    user_group_map = {} # UserID -> [GroupName1, GroupName2] helper for mapping
    
    try:
        count = 0 
        for group_id, group_name in groups.items():
            paginator = identitystore_client.get_paginator('list_group_memberships')
            members = []
            for page in paginator.paginate(IdentityStoreId=identity_store_id, GroupId=group_id):
                for member in page['GroupMemberships']:
                    member_id = member['MemberId']['UserId']
                    members.append(member_id)
                    
                    if member_id not in user_group_map:
                        user_group_map[member_id] = []
                    # group_info is now a dict, so access Name
                    user_group_map[member_id].append(group_name['Name'])
            
            group_members[group_id] = members
            count += 1
            if count % 10 == 0:
                logger.info(f"Processed memberships for {count} groups...")
                
        logger.info("Finished processing group memberships.")
        return group_members, user_group_map
    except ClientError as e:
        logger.error(f"Error listing group memberships: {e}")
        raise

def list_all_accounts(org_client):
    """Fetch all AWS accounts in the organization."""
    accounts = {}
    paginator = org_client.get_paginator('list_accounts')
    try:
        for page in paginator.paginate():
            for account in page['Accounts']:
                # Filter for active accounts if needed, but for review listing all might be safer
                if account['Status'] == 'ACTIVE':
                    accounts[account['Id']] = account['Name']
        logger.info(f"Fetched {len(accounts)} active accounts.")
        return accounts
    except ClientError as e:
        logger.error(f"Error listing accounts: {e}")
        raise

def get_permission_sets(sso_admin_client, instance_arn):
    """Fetch all permission sets."""
    permission_sets = {} # Arn -> Name
    paginator = sso_admin_client.get_paginator('list_permission_sets')
    try:
        for page in paginator.paginate(InstanceArn=instance_arn):
            for arn in page['PermissionSets']:
                # Get details to get the name
                # Optimizing: List gives ARNs, describe gives name. 
                # This might be slow if many sets.
                try: 
                    details = sso_admin_client.describe_permission_set(
                        InstanceArn=instance_arn,
                        PermissionSetArn=arn
                    )
                    permission_sets[arn] = {
                        'Name': details['PermissionSet']['Name'],
                        'Description': details['PermissionSet'].get('Description', 'N/A'),
                        'ManagedPolicies': [],
                        'InlinePolicy': 'None',
                        'CustomerManagedPolicies': []
                    }
                    
                    # 1. Fetch AWS Managed Policies
                    try:
                        mp_paginator = sso_admin_client.get_paginator('list_managed_policies_in_permission_set')
                        for mp_page in mp_paginator.paginate(InstanceArn=instance_arn, PermissionSetArn=arn):
                            for mp in mp_page['AttachedManagedPolicies']:
                                permission_sets[arn]['ManagedPolicies'].append(mp['Name'])
                    except ClientError as e:
                        logger.warning(f"  - Could not list managed policies for {permission_sets[arn]['Name']}: {e}")

                    # 2. Fetch Inline Policy
                    try:
                        inline_resp = sso_admin_client.get_inline_policy_for_permission_set(
                            InstanceArn=instance_arn, 
                            PermissionSetArn=arn
                        )
                        if inline_resp.get('InlinePolicy'):
                            permission_sets[arn]['InlinePolicy'] = "Present (See Console)" # Keeping it brief for Excel, or could dump JSON
                    except ClientError as e:
                        # Some PS might not have inline policies or just error out
                        pass 

                    # 3. Fetch Customer Managed Policies
                    try:
                        cmp_paginator = sso_admin_client.get_paginator('list_customer_managed_policy_references_in_permission_set')
                        for cmp_page in cmp_paginator.paginate(InstanceArn=instance_arn, PermissionSetArn=arn):
                            for cmp in cmp_page['CustomerManagedPolicyReferences']:
                                permission_sets[arn]['CustomerManagedPolicies'].append(cmp['Name'])
                    except ClientError as e:
                        pass
                        
                except ClientError as e:
                    logger.warning(f"Could not describe permission set {arn}: {e}")
        logger.info(f"Fetched {len(permission_sets)} permission sets.")
        return permission_sets
    except ClientError as e:
        logger.error(f"Error listing permission sets: {e}")
        raise

def map_assignments(sso_admin_client, instance_arn, accounts, permission_sets, users, groups, user_group_map):
    """
    Iterate through accounts to find provisioned permission sets, then list assignments.
    Flatten the data into a list of dictionaries for export.
    """
    data_rows = []
    
    for account_id, account_name in accounts.items():
        logger.info(f"Scanning account: {account_name} ({account_id})")
        
        # 1. List Permission Sets provisioned to this account
        # Note: This avoids checking every permission set against every account
        prov_paginator = sso_admin_client.get_paginator('list_permission_sets_provisioned_to_account')
        try:
            account_permission_sets = []
            for page in prov_paginator.paginate(InstanceArn=instance_arn, AccountId=account_id):
                account_permission_sets.extend(page['PermissionSets'])
            
            if not account_permission_sets:
                continue

            # 2. For each provisioned permission set, list assignments
            for ps_arn in account_permission_sets:
                ps_data = permission_sets.get(ps_arn, {'Name': "Unknown Permission Set"})
                ps_name = ps_data['Name']
                
                assign_paginator = sso_admin_client.get_paginator('list_account_assignments')
                for page in assign_paginator.paginate(
                    InstanceArn=instance_arn,
                    AccountId=account_id,
                    PermissionSetArn=ps_arn
                ):
                    for assignment in page['AccountAssignments']:
                        principal_type = assignment['PrincipalType']
                        principal_id = assignment['PrincipalId']
                        
                        # Case 1: Direct User Assignment
                        if principal_type == 'USER':
                            user_details = users.get(principal_id, {'UserName': 'Unknown', 'Email': 'Unknown'})
                            data_rows.append({
                                'Account Name': account_name,
                                'Account ID': account_id,
                                'Permission Set': ps_name,
                                'Principal Type': 'USER',
                                'Principal Name': user_details['UserName'],
                                'User Email': user_details['Email'],
                                'Access Method': 'DIRECT'
                            })
                            
                        # Case 2: Group Assignment
                        elif principal_type == 'GROUP':
                            group_info = groups.get(principal_id, {'Name': 'Unknown Group'})
                            group_name = group_info['Name']
                            # Get all users in this group
                            # We need to inverse the group->user map we made or iterate users
                            # In list_group_memberships we returned group_members dict: GroupID -> [UserIDs]
                            
                            # Re-fetch members from the dict passed in (users/groups need to be passed correctly)
                            # Let's fix the logic to use what we have.
                            # We need to pass `group_members` (Group ID -> List of User IDs) into this function
                            pass # Handled below by iterating the group members
                            
        except ClientError as e:
            logger.error(f"Error scanning account {account_id}: {e}")
            
    return data_rows

def send_email_with_attachment(output_file):
    """
    Send email with the Excel report as attachment using SMTP.
    Email credentials are optional - if not configured, email sending is skipped silently.
    """
    try:
        # Load environment variables
        load_dotenv()

        # Get email configuration from environment variables
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        email_username = os.getenv('EMAIL_USERNAME')
        email_password = os.getenv('EMAIL_PASSWORD')
        email_recipients = os.getenv('EMAIL_RECIPIENTS')
        email_sender_name = os.getenv('EMAIL_SENDER_NAME', 'AWS Identity Center Review System')
        email_subject = os.getenv('EMAIL_SUBJECT', 'AWS Identity Center Access Review Report')

        # Check if email is configured (server and recipients are required, credentials are optional for relay hosts)
        if not smtp_server or not email_recipients:
            logger.info("Email notification skipped (server or recipients not configured)")
            return False

        # Create message
        msg = MIMEMultipart()
        msg['From'] = f"{email_sender_name} <{email_username}>"
        msg['To'] = email_recipients
        msg['Subject'] = f"{email_subject} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        # Email body
        body = f"""
Dear Team,

Please find attached the latest AWS Identity Center Access Review Report.

Report Details:
- Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- File: {output_file}

This report contains:
1. User assignments to AWS accounts and permission sets
2. Group information and memberships
3. Permission set details with associated policies

Please review the access assignments and ensure they align with your security policies.

Best regards,
AWS Identity Center Review System
        """
        msg.attach(MIMEText(body, 'plain'))

        # Attach the Excel file
        if os.path.exists(output_file):
            with open(output_file, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f"attachment; filename= {output_file}")
                msg.attach(part)
        else:
            logger.error(f"Report file {output_file} not found. Cannot send email.")
            return False

        # Send email
        logger.info("Sending email notification...")
        server = smtplib.SMTP(smtp_server, smtp_port)

        # Only attempt STARTTLS and login if credentials are provided (for authenticated SMTP)
        # Skip authentication for relay hosts that don't require it
        if email_username and email_password:
            server.starttls()
            server.login(email_username, email_password)
        else:
            # For relay hosts without authentication, just establish connection
            logger.info("Using relay host without authentication")

        # Send to multiple recipients
        # Use a default from address if no username is provided
        from_address = email_username if email_username else f"noreply@{smtp_server}"
        recipients_list = [email.strip() for email in email_recipients.split(',')]
        server.sendmail(from_address, recipients_list, msg.as_string())
        server.quit()

        logger.info(f"Email sent successfully to: {', '.join(recipients_list)}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False

def main():
    try:
        # 1. Setup Clients
        logger.info("Initializing clients...")
        # You might want to allow region selection via args
        identitystore, sso_admin, orgs = get_clients() 
        
        # 2. Get Instance Info
        logger.info("Fetching SSO Instance info...")
        instance_arn, identity_store_id = get_sso_instance(sso_admin)
        logger.info(f"Instance ARN: {instance_arn}")
        
        # 3. Fetch Core Data
        logger.info("Fetching Users...")
        users = list_all_users(identitystore, identity_store_id)
        
        logger.info("Fetching Groups...")
        groups = list_all_groups(identitystore, identity_store_id)
        
        logger.info("Fetching Group Memberships...")
        group_members, user_group_map = list_group_memberships(identitystore, identity_store_id, groups)
        
        logger.info("Fetching Accounts...")
        accounts = list_all_accounts(orgs)
        
        logger.info("Fetching Permission Sets...")
        permission_sets = get_permission_sets(sso_admin, instance_arn)
        
        # 4. Map Assignments and Build Report
        logger.info("Mapping assignments to users...")
        final_report = []
        
        # The logic in 'map_assignments' was slightly incomplete regarding Group expansion.
        # Let's implement the core iteration logic here for clarity.
        
        for account_id, account_name in accounts.items():
            logger.info(f"Scanning account: {account_name} ({account_id})")
            
            # Get Provisioned Permission Sets
            try:
                prov_paginator = sso_admin.get_paginator('list_permission_sets_provisioned_to_account')
                account_permission_sets = []
                for page in prov_paginator.paginate(InstanceArn=instance_arn, AccountId=account_id):
                    account_permission_sets.extend(page['PermissionSets'])
            except ClientError as e:
                logger.error(f"Failed to list provisioned permission sets for {account_name}: {e}")
                continue
                
            for ps_arn in account_permission_sets:
                ps_data = permission_sets.get(ps_arn, {'Name': "Unknown Permission Set"})
                ps_name = ps_data['Name']
                
                # List Assignments
                try:
                    assign_paginator = sso_admin.get_paginator('list_account_assignments')
                    for page in assign_paginator.paginate(InstanceArn=instance_arn, AccountId=account_id, PermissionSetArn=ps_arn):
                        for assignment in page['AccountAssignments']:
                            principal_type = assignment['PrincipalType']
                            principal_id = assignment['PrincipalId']
                            
                            if principal_type == 'USER':
                                # Direct Assignment
                                u = users.get(principal_id, {})
                                final_report.append({
                                    'Account Name': account_name,
                                    'Account ID': account_id,
                                    'Permission Set': ps_name,
                                    'Assignment Type': 'Direct User',
                                    'Group Name': 'N/A',
                                    'User Name': u.get('UserName', 'Unknown'),
                                    'User Email': u.get('Email', 'Unknown')
                                })
                            
                            elif principal_type == 'GROUP':
                                # Group Assignment - Expand to all members
                                g_info = groups.get(principal_id, {'Name': 'Unknown Group'})
                                g_name = g_info['Name']
                                member_ids = group_members.get(principal_id, [])
                                
                                if not member_ids:
                                    # Group has assignment but no members
                                    final_report.append({
                                        'Account Name': account_name,
                                        'Account ID': account_id,
                                        'Permission Set': ps_name,
                                        'Assignment Type': 'Group (Empty)',
                                        'Group Name': g_name,
                                        'User Name': 'N/A',
                                        'User Email': 'N/A'
                                    })
                                else:
                                    for m_id in member_ids:
                                        u = users.get(m_id, {})
                                        final_report.append({
                                            'Account Name': account_name,
                                            'Account ID': account_id,
                                            'Permission Set': ps_name,
                                            'Assignment Type': 'Group',
                                            'Group Name': g_name,
                                            'User Name': u.get('UserName', 'Unknown'),
                                            'User Email': u.get('Email', 'Unknown')
                                        })
                except ClientError as e:
                    logger.error(f"Failed to list assignments for {ps_name} in {account_name}: {e}")

        # 5. Export to Excel
        if not final_report:
            logger.warning("No assignments found!")
        else:
            logger.info(f"Generating Excel report with {len(final_report)} rows...")
            df_assignments = pd.DataFrame(final_report)
            
            # Sort by User Name for user-centric view
            df_assignments = df_assignments.sort_values(by=['User Name', 'Account Name'])
            
            # Create DataFrames for Metadata Sheets
            # groups dict is {Id: {Name, Description}}
            group_rows = [{'Group ID': k, 'Group Name': v['Name'], 'Description': v['Description']} for k, v in groups.items()]
            df_groups = pd.DataFrame(group_rows)
            
            # permission_sets dict is {Arn: {Name, Description, ManagedPolicies[], InlinePolicy, CustomerManagedPolicies[]}}
            ps_rows = []
            for k, v in permission_sets.items():
                ps_rows.append({
                    'Permission Set ARN': k, 
                    'Permission Set Name': v['Name'], 
                    'Description': v['Description'],
                    'AWS Managed Policies': ", ".join(v['ManagedPolicies']),
                    'Inline Policy': v['InlinePolicy'],
                    'Customer Managed Policies': ", ".join(v['CustomerManagedPolicies'])
                })
            df_permission_sets = pd.DataFrame(ps_rows)

            output_file = 'AWS_Identity_Center_Review.xlsx'
            logger.info(f"Saving to {output_file}...")
            
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df_assignments.to_excel(writer, sheet_name='Assignments', index=False)
                df_groups.to_excel(writer, sheet_name='Groups', index=False)
                df_permission_sets.to_excel(writer, sheet_name='Permission Sets', index=False)
                
                # Auto-adjust column widths
                for sheet in writer.sheets.values():
                    for col in sheet.columns:
                        max_length = 0
                        column = col[0].column_letter # Get the column name
                        for cell in col:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(cell.value)
                            except:
                                pass
                        adjusted_width = (max_length + 2)
                        sheet.column_dimensions[column].width = min(adjusted_width, 100) # Cap width

            logger.info(f"Successfully saved report to {output_file}")

            # 6. Send email notification with report (optional)
            email_sent = send_email_with_attachment(output_file)
            if email_sent:
                logger.info("Report generation and email notification completed successfully!")
            elif email_sent is False and logger.level <= logging.INFO:
                # Only show warning if email was configured but failed
                # If email_sent is False due to missing config, send_email_with_attachment
                # already logged "Email notification skipped (not configured)" at INFO level
                pass

    except Exception as main_e:
        logger.error(f"Script failed: {main_e}")
        raise

if __name__ == '__main__':
    main()
