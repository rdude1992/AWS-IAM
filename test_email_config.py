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

        # Check minimum required configuration (server and recipients are required)
        if not smtp_server or not email_recipients:
            logger.info("Email configuration incomplete (server and recipients are required)")
            logger.info("Required variables: SMTP_SERVER, EMAIL_RECIPIENTS")
            logger.info("Optional variables: EMAIL_USERNAME, EMAIL_PASSWORD (for authenticated SMTP)")
            return None  # Return None to indicate feature not configured

        # If we have server and recipients, config is valid
        # Check if credentials are provided for authentication
        has_credentials = bool(email_username and email_password)

        if has_credentials:
            logger.info("Email configured with authentication")
        else:
            logger.info("Email configured for relay host (no authentication required)")
            return True  # Config is valid for relay host

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
    result = test_email_config()
    if result is True:
        logger.info("Email configuration is valid and ready to use!")
    elif result is None:
        logger.info("Email configuration not configured (optional feature skipped)")
    else:
        logger.error("Email configuration needs to be fixed before use.")
