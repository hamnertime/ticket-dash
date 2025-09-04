#!/usr/bin/env python3

import datetime
import os
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# This script generates a self-signed SSL certificate and a private key.
# These files (cert.pem and key.pem) are used by the Flask application
# to enable HTTPS on port 443.

# --- Configuration ---
# You can change these values if needed.
KEY_FILE = "key.pem"
CERT_FILE = "cert.pem"
VALIDITY_DAYS = 3650  # Certificate will be valid for 10 years
KEY_STRENGTH = 2048   # RSA key strength in bits

# Subject information for the certificate.
# CN (Common Name) is the most important field. For local testing, 'localhost' is fine.
# If you access the dashboard from other machines, change 'localhost' to the
# server's IP address or its DNS name (e.g., tickets.integotec.local).
COUNTRY = "US"
STATE = "Oregon"
CITY = "Roseburg"
ORGANIZATION = "Integotec"
COMMON_NAME = "localhost"

def generate_self_signed_cert():
    """
    Generates a private key and a self-signed certificate and saves them to files.
    """
    print(f"Generating a {KEY_STRENGTH}-bit RSA private key...")

    # Generate our private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=KEY_STRENGTH,
        backend=default_backend()
    )

    # Define the subject of the certificate
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, COUNTRY),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, STATE),
        x509.NameAttribute(NameOID.LOCALITY_NAME, CITY),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORGANIZATION),
        x509.NameAttribute(NameOID.COMMON_NAME, COMMON_NAME),
    ])

    # The issuer is the same as the subject in a self-signed certificate
    issuer = subject

    # Build the certificate
    cert_builder = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        # Certificate will be valid for VALIDITY_DAYS from now
        datetime.datetime.utcnow() + datetime.timedelta(days=VALIDITY_DAYS)
    ).add_extension(
        # Basic constraints, marking it as not a CA certificate
        x509.BasicConstraints(ca=False, path_length=None), critical=True,
    )

    # Sign the certificate with our private key
    certificate = cert_builder.sign(private_key, hashes.SHA256(), default_backend())

    # Write private key to PEM file
    try:
        with open(KEY_FILE, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        print(f"✅ Private key saved to: {KEY_FILE}")
    except IOError as e:
        print(f"❌ Error writing private key file: {e}")
        return

    # Write certificate to PEM file
    try:
        with open(CERT_FILE, "wb") as f:
            f.write(certificate.public_bytes(serialization.Encoding.PEM))
        print(f"✅ Certificate saved to: {CERT_FILE}")
    except IOError as e:
        print(f"❌ Error writing certificate file: {e}")
        return

    print("\nSuccess! Place these two files in the same directory as your main.py script.")


if __name__ == "__main__":
    # Check if files already exist to avoid accidental overwrites
    if os.path.exists(KEY_FILE) or os.path.exists(CERT_FILE):
        overwrite = input(
            f"Warning: '{KEY_FILE}' or '{CERT_FILE}' already exists. Overwrite? (y/n): "
        ).lower()
        if overwrite != 'y':
            print("Operation cancelled.")
        else:
            generate_self_signed_cert()
    else:
        generate_self_signed_cert()
