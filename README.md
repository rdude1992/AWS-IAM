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
