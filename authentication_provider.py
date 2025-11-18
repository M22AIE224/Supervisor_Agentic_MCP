import os
from aia_auth import auth
import base64
import httpx
import math
import time
import uuid


import os
from dotenv import load_dotenv

load_dotenv('.env', override=True)
client_id = os.getenv("CLIENT_ID")

client_secret = os.getenv("CLIENT_SECRET")
use_sso = os.getenv("USE_SSO") #False
server_side_token_refersh = False


print("Client ID " + client_id)
print("Client Sercret " + client_secret)
print("USE_SSO " + use_sso)


def get_correlation_id():
    return str(uuid.uuid4())

def validate_client_credentials():
    if client_id == 'Insert_your_client_id_here' or client_id is None or client_secret == 'Insert_your_client_secret_here' or client_secret is None:
        print("*** Please set the CLIENT_ID & CLIENT_SECRET in environment variables or set Use_SSO to true. ***")
        raise Exception("Invalid client credentials")
    else:
        print("Using Client Credentials")

# If using Inidividual plan, set USE_SSO to true in .env
if use_sso:
    print("Using Single Sign-On (SSO)")
else:
    validate_client_credentials()


import requests
import zipfile
import io
import certifi

def update_certifi():
    # URL to download the Dell certificates zip file
    url = "https://pki.dell.com//Dell%20Technologies%20PKI%202018%20B64_PEM.zip"
    print("Downloading Dell certificates zip from:", url)
    response = requests.get(url)
    # Use raise_for_status() for concise error checking
    response.raise_for_status()
    print("Downloaded certificate zip, size:", len(response.content), "bytes")

    # Determine the location of the certifi bundle
    cert_path = certifi.where()
    print("Certifi bundle path:", cert_path)

    # Define the names of the certificates within the zip file
    dell_root_cert_name = "Dell Technologies Root Certificate Authority 2018.pem"
    dell_issuing_cert_name = "Dell Technologies Issuing CA 101_new.pem"

    # Append the certificates directly from the zip archive in memory.
    print("Appending Dell certificates to certifi bundle...")
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            # Read certificate contents directly from the zip file in memory
            # Ensure decoding from bytes to string (assuming UTF-8)
            root_cert_content = z.read(dell_root_cert_name).decode('utf-8')
            issuing_cert_content = z.read(dell_issuing_cert_name).decode('utf-8')

            # Append the certificates to the certifi bundle
            # (Make sure you have backup of certifi bundle if needed.)
            with open(cert_path, "a") as bundle:
                bundle.write("\n")
                bundle.write(root_cert_content)
                bundle.write("\n") # Ensure newline after first cert
                bundle.write(issuing_cert_content)
                bundle.write("\n") # Ensure newline after second cert

        print("Dell certificates successfully added to certifi bundle.")

    except KeyError as e:
        # Handle case where expected certificate file is not in the zip
        print(f"Error: Certificate file '{e}' not found in the zip archive.")
    except Exception as e:
        # Handle other potential errors during processing
        print(f"An error occurred during certificate appending: {e}")


update_certifi()

def get_default_headers_based_on_authentication():
    default_headers = {
            "x-correlation-id": get_correlation_id(),
            'accept': '*/*',
            'Content-Type': 'application/json'
        }
    if use_sso:
        auth = AuthenticationProvider()
        default_headers['Authorization'] = 'Bearer ' + auth.generate_auth_token()
    else:
        if server_side_token_refersh:
            auth = AuthenticationProvider()
            default_headers['Authorization'] = 'Basic ' + auth.get_basic_credentials()
            
    print('Authorization' + default_headers['Authorization'] )
    return default_headers

import httpx

def get_http_client_based_on_authentication(httpx_client_class):
    if use_sso:
        http_client=httpx_client_class(verify=certifi.where())
    else:
        if server_side_token_refersh:
            http_client=httpx_client_class(verify=certifi.where())
        else:
            auth = AuthenticationProviderWithClientSideTokenRefresh()
            http_client=httpx_client_class(auth=auth,verify=certifi.where())
    return http_client


class AuthenticationProvider:
    def __init__(self):
        """
        Initializes the AuthenticationProvider class.

        Initializes the use_sso, client_id and client_secret instance variables.
        """
        self.use_sso = os.getenv("USE_SSO").lower() == "true"
        # Below properties are applicable to OAUTH only
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret = os.getenv("CLIENT_SECRET")
        self.redirect_url = os.getenv("AIA_REDIRECT_URI")
        self.callback_url=os.getenv("AIA_REDIRECT_URI")

    def generate_auth_token(self):
        """
        Generates and returns an authentication token based on the configured method.

        The method defaults to `client_credentials` if `use_sso` is not explicitly
        set to "true".

        Returns:
            str: The generated authentication token.
        """
        if self.use_sso:
            return self._sso()
                
        return self._get_bearer_token()
    
    def get_basic_credentials(self):
        """
        Authenticates a request using either Single Sign-On or Client & Secret based on the value of USE_SSO.
        
        Parameters:
            request: The request object to authenticate.
        
        Returns:
            The authenticated request object.
        """
        self._validate_client_credentials()
        return base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode()).decode()

    def _get_bearer_token(self):
        """
        Generates an authentication token using the Client Credentials flow.

        This method assumes that `client_id` and `client_secret` are globally
        available or passed in a different context. It first validates these
        credentials before requesting a token.

        Returns:
            str: The authentication token.
        """
        self._validate_client_credentials()
        return auth.client_credentials(self.client_id, self.client_secret).token

    def _sso(self):
        """
        Generates an authentication token using the Single Sign-On (SSO) flow.

        This method leverages the `auth.sso()` function to obtain a token,
        which typically involves a user interaction or a pre-configured
        session.

        Returns:
            str: The authentication token.
        """
        access_token = auth.sso()
        return access_token.token    
    
    def _validate_client_credentials(self):
        """
        Validates client credentials. Checks if client ID and client secret are set and not equal to default values.

        Parameters:
            self (AuthenticationProvider): The instance of the class that this function is a part of.

        Returns:
            None: If the client credentials are valid, the function does not return anything. If the client credentials are invalid, the function raises an exception.
        """
        if self.client_id == 'Insert_your_client_id_here' or self.client_id is None or self.client_secret == 'Insert_your_client_secret_here' or self.client_secret is None:
            print("*** Please set the CLIENT_ID & CLIENT_SECRET in environment variables or set Use_SSO to true. ***")
            raise Exception("Invalid client credentials")

class AuthenticationProviderWithClientSideTokenRefresh(httpx.Auth):
    def __init__(self):
        """
        Initializes the AuthenticationProviderWithTokenRefresh class.

        Initializes the client_id, client_secret, last_refreshed, and valid_until instance variables.
        """
        # Below properties are applicableto OAUTH only
        self.client_id = os.getenv("CLIENT_ID")
        self.client_secret = os.getenv("CLIENT_SECRET")
        self.last_refreshed = math.floor(time.time())
        self.valid_until = math.floor(time.time()) - 1
    
    def auth_flow(self, request):
        """
        Authenticates a request using either Single Sign-On or Client & Secret based on the value of USE_SSO.
        
        Parameters:
            request: The request object to authenticate.
        
        Returns:
            The authenticated request object.
        """
        if "x-correlation-id" not in request.headers:
            request.headers["x-correlation-id"] = str(uuid.uuid4())
        request.headers["Authorization"] = f"Bearer {self.get_bearer_token()}"
        yield request

    def get_bearer_token(self):
        """
        Returns the bearer token. If the current token has expired, it generates a new one using the client ID and secret.
        
        Returns:
            str: The generated or existing bearer token.
        """
        if self._is_expired():
            print("Generating new token...\n")
            self.last_refreshed = math.floor(time.time())
            _resp = auth.client_credentials(self.client_id, self.client_secret)
            self.token = _resp.token
            self.expires_in = _resp.expires_in
            self.valid_until = self.last_refreshed + self.expires_in
        else:
            print("Token not expired, using cached token...\n")
        return self.token

    def _is_expired(self):
        """
        Checks if the current time is greater than or equal to the valid_until attribute.

        Returns:
            bool: True if the current time is greater than or equal to valid_until, False otherwise.
        """
        return time.time() >= self.valid_until