"""
Porkbun Certificate Sync Application
"""
import warnings

# Suppress paramiko/cryptography deprecation warnings about TripleDES
# CryptographyDeprecationWarning is a UserWarning subclass
warnings.filterwarnings('ignore', message='.*TripleDES.*')

__version__ = "1.0.0"
