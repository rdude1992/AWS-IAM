# AWS IAM Identity Center Review Automation

This project contains a Python script to automate the review of AWS IAM Identity Center (formerly AWS SSO) users and their assignments for audit and compliance purposes (e.g., PCI).

## Features

- **Fetches all Users and Groups** from the AWS Identity Store.
- **Maps IAM Permissions**: Identifies which Permission Sets are assigned to which Users/Groups across all AWS Accounts in the Organization.
- **Handles Group Expansion**: Correctly expands Group assignments to list individual user access.
- **User-Centric View**: Sorts assignments by User Name for easier review.
- **Metadata Export**: Includes descriptions for Groups and Permission Sets.
- **Excel Export**: Generates a multi-sheet Excel report:
    - **Assignments**: Detailed list of who has access to what.
    - **Groups**: List of groups with descriptions.
    - **Permission Sets**: List of permission sets with descriptions.
- **Email Notifications**: Automatically sends the generated report as an email attachment to configured recipients.

## Prerequisites

- Python 3.x
- Valid AWS Credentials configured (e.g., `~/.aws/credentials` or environment variables).

## Installation

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

Run the script:
```bash
python aws_identity_center_review.py
```

The script will generate `AWS_Identity_Center_Review.xlsx` in the same directory.

## Email Configuration (Optional)

The script can automatically send the generated report as an email attachment. To enable this feature:

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and configure your email settings:
   ```bash
   # Required settings
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   EMAIL_USERNAME=your-email@gmail.com (optional- keep blank if no auth required)
   EMAIL_PASSWORD=your-app-password (optional- keep blank if no auth required)
   EMAIL_RECIPIENTS=admin@company.com,security@company.com

   # Optional settings
   EMAIL_SENDER_NAME=AWS Identity Center Review System
   EMAIL_SUBJECT=AWS Identity Center Access Review Report
   ```

### Email Provider Setup

**Gmail:**
- Use `smtp.gmail.com` as SMTP_SERVER
- Use port `587` (TLS) or `465` (SSL)
- Generate an "App Password" instead of using your regular password:
  1. Enable 2FA on your Google account
  2. Go to Google Account settings > Security > App passwords
  3. Generate a password for "Mail"

**Other Providers:**
- Outlook/Hotmail: `smtp-mail.outlook.com:587`
- Yahoo: `smtp.mail.yahoo.com:587`
- Corporate SMTP: Contact your IT team for server details

### Security Notes

- Store `.env` securely and never commit it to version control
- Use app-specific passwords when available
- Consider using dedicated service accounts for automated emails

## AWS Permissions Required

The AWS credentials used to run this script must have the following permissions:

### Identity Store
- `identitystore:ListUsers`
- `identitystore:ListGroups`
- `identitystore:ListGroupMemberships`

### SSO Admin (Identity Center)
- `sso:ListInstances`
- `sso:ListPermissionSets`
- `sso:DescribePermissionSet`
- `sso:ListAccountAssignments`
- `sso:ListPermissionSetsProvisionedToAccount`
- `sso:ListManagedPoliciesInPermissionSet`
- `sso:GetInlinePolicyForPermissionSet`
- `sso:ListCustomerManagedPolicyReferencesInPermissionSet`

### Organizations
- `organizations:ListAccounts` (Used to map Account IDs to friendly names)

## Limitations

- **Last Login**: The script does **not** fetch user "Last Login" timestamps. This information is not directly available in the Identity Store API and requires complex CloudTrail analysis which is outside the scope of this lightweight reviewer.
- **Groups**: Empty groups (groups with assignments but no members) are listed with "N/A" for user details.
