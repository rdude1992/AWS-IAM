#!/usr/bin/env python3
"""
Test script to validate email configuration without sending actual emails.
"""
import os
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_email_config():
    """Test email configuration by validating environment variables."""
    try:
        # Load environment variables
        load_dotenv()

        # Get email configuration from environment variables
        smtp_server = os.getenv('SMTP_SERVER')
        smtp_port = os.getenv('SMTP_PORT', 587)
        email_username = os.getenv('EMAIL_USERNAME')
        email_password = os.getenv('EMAIL_PASSWORD')
        email_recipients = os.getenv('EMAIL_RECIPIENTS')
        email_sender_name = os.getenv('EMAIL_SENDER_NAME', 'AWS Identity Center Review System')
        email_subject = os.getenv('EMAIL_SUBJECT', 'AWS Identity Center Access Review Report')

        # Validate required environment variables
        missing_vars = []
        if not smtp_server:
            missing_vars.append('SMTP_SERVER')
        if not email_username:
            missing_vars.append('EMAIL_USERNAME')
        if not email_password:
            missing_vars.append('EMAIL_PASSWORD')
        if not email_recipients:
            missing_vars.append('EMAIL_RECIPIENTS')

        if missing_vars:
            logger.warning("Email configuration incomplete. Missing required variables:")
            for var in missing_vars:
                logger.warning(f"  - {var}")
            logger.info("Please set these variables in your .env file")
            return False

        # Display configuration (masking password)
        logger.info("Email configuration validated successfully!")
        logger.info(f"SMTP Server: {smtp_server}:{smtp_port}")
        logger.info(f"Username: {email_username}")
        logger.info(f"Password: {'*' * len(email_password)}")
        logger.info(f"Recipients: {email_recipients}")
        logger.info(f"Sender Name: {email_sender_name}")
        logger.info(f"Subject: {email_subject}")

        # Test SMTP connection (without sending)
        import smtplib
        try:
            logger.info("Testing SMTP connection...")
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            server.starttls()
            server.login(email_username, email_password)
            server.quit()
            logger.info("SMTP connection test successful!")
            return True
        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False

    except Exception as e:
        logger.error(f"Email configuration test failed: {e}")
        return False

if __name__ == '__main__':
    logger.info("Testing email configuration...")
    success = test_email_config()
    if success:
        logger.info("Email configuration is valid and ready to use!")
    else:
        logger.error("Email configuration needs to be fixed before use.")