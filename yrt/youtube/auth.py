"""Authentication functions for YouTube API."""

# Standard library
import ast
import base64
import json
import os
from typing import Any

# Third-party
import pyyoutube as pyt  # type: ignore[import-untyped]
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

# Local
from .. import paths
from ..exceptions import CredentialsError, YouTubeServiceError, FileAccessError
from . import utils


def encode_key(json_path: str, export_dir: str | None = None, export_name: str | None = None) -> None:
    """Encode a JSON authentication file to base64.

    Args:
        json_path: File path to authentication JSON file.
        export_dir: Export directory.
        export_name: Export file name.

    Raises:
        FileAccessError: If the file path is invalid or the file does not exist.
    """
    path_split = json_path.split('/')
    file_name = path_split[-1].removesuffix('.json')

    if export_dir is None:
        export_dir = json_path.removesuffix(f'{file_name}.json')

    if export_name is None:
        export_name = f'{file_name}_b64.txt'

    if '_tokens' not in json_path:
        if utils.history:
            utils.history.critical('FORBIDDEN ACCESS. Invalid file path.')
        raise FileAccessError('FORBIDDEN ACCESS. Invalid file path.')

    if not os.path.exists(json_path):
        if utils.history:
            utils.history.error('%s file does not exist.', json_path)
        raise FileAccessError(f'{json_path} file does not exist.')

    with open(json_path, 'r', encoding='utf8') as json_file:
        key_dict = json.load(json_file)

    key_str = json.dumps(key_dict).encode('utf-8')
    key_b64 = base64.urlsafe_b64encode(key_str)

    with open(export_dir + export_name, 'wb') as key_file:
        key_file.write(key_b64)


def create_service_local(log: bool = True) -> pyt.Client:
    """Create a GCP service for YouTube API V3.

    Mostly inspired by this: https://learndataanalysis.org/google-py-file-source-code/

    Args:
        log: Whether to apply logging or not.

    Returns:
        A Google API service object build with 'googleapiclient.discovery.build'.

    Raises:
        YouTubeServiceError: If the service creation fails.
    """
    oauth_file = str(paths.OAUTH_JSON)  # OAUTH 2.0 ID path
    scopes = ['https://www.googleapis.com/auth/youtube', 'https://www.googleapis.com/auth/youtube.force-ssl']
    instance_fail_message = 'Failed to create service instance for YouTube'
    cred = None

    if os.path.exists(paths.CREDENTIALS_JSON):
        cred = Credentials.from_authorized_user_file(str(paths.CREDENTIALS_JSON))  # Retrieve credentials

    if not cred or not cred.valid:  # Cover outdated or non-existant credentials
        if cred and cred.expired and cred.refresh_token:
            try:
                cred.refresh(Request())

            except RefreshError:
                if utils.history:
                    utils.history.info('Credentials can not be refreshed. New credentials needed.')
                flow = InstalledAppFlow.from_client_secrets_file(oauth_file, scopes)  # Create a Flow from 'oauth_file'
                cred = flow.run_local_server()  # Run the authentication process

        else:
            # Create the authentification Flow from 'oauth_file' and then run the authentication process
            flow = InstalledAppFlow.from_client_secrets_file(oauth_file, scopes)
            cred = flow.run_local_server()

        with open(paths.CREDENTIALS_JSON, 'w') as cred_file:  # Save credentials as a JSON file
            # noinspection PyTypeChecker
            json.dump(ast.literal_eval(cred.to_json()), cred_file, ensure_ascii=False, indent=4)

    try:
        service = pyt.Client(client_id=cred.client_id, client_secret=cred.client_secret, access_token=cred.token)
        if log and utils.history:
            utils.history.info('YouTube service created successfully.')

        return service

    except (pyt.error.PyYouTubeException, ValueError, AttributeError) as error:
        if log and utils.history:
            utils.history.critical('(%s) %s', error, instance_fail_message)

        raise YouTubeServiceError(f'{instance_fail_message}: {error}')


def create_service_workflow() -> tuple[pyt.Client, str]:
    """Create a GCP service for YouTube API V3, for usage in GitHub Actions workflow.

    Returns:
        Tuple of (service, creds_b64) where service is a Google API service object.

    Raises:
        CredentialsError: If credentials are missing or cannot be refreshed.
        YouTubeServiceError: If the service creation fails.
    """

    def import_env_var(var_name: str) -> dict[str, Any]:
        """Import environment variable and perform base64 decoding.

        Args:
            var_name: Environment variable name.

        Returns:
            Decoded value as a dictionary.

        Raises:
            CredentialsError: If the environment variable is not found.
        """
        v_b64 = os.environ.get(var_name)  # Get environment variable
        if v_b64 is None:
            raise CredentialsError(f'Environment variable {var_name} not found')
        v_str = base64.urlsafe_b64decode(v_b64).decode(encoding='utf8')  # Decode
        value = ast.literal_eval(v_str)  # Eval
        return value  # type: ignore[no-any-return]

    creds_b64 = os.environ.get('CREDS_B64')  # Initiate the Base64 version of the Credentials object
    creds_dict = import_env_var(var_name='CREDS_B64')  # Import pre-registered credentials
    creds = Credentials.from_authorized_user_info(creds_dict)  # Conversion to a suitable object
    instance_fail_message = 'Failed to create service instance for YouTube'

    if not creds.valid:  # Cover outdated credentials
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())  # Refresh token

            # Get refreshed token as JSON-like string
            creds_str = json.dumps(ast.literal_eval(creds.to_json())).encode('utf-8')

            creds_b64 = str(base64.urlsafe_b64encode(creds_str))[2:-1]  # Encode token
            os.environ['CREDS_B64'] = creds_b64  # Update environment variable value
            if utils.history:
                utils.history.info('API credentials refreshed.')

        else:
            if utils.history:
                utils.history.critical('ERROR: Unable to refresh credentials. Check Google API OAUTH parameter.')
            raise CredentialsError('Unable to refresh credentials. Check Google API OAUTH parameter.')

    try:
        service = pyt.Client(client_id=creds.client_id, client_secret=creds.client_secret, access_token=creds.token)
        if utils.history:
            utils.history.info('YouTube service created successfully.')
        # creds_b64 is guaranteed to be str at this point (import_env_var raises if missing)
        assert creds_b64 is not None
        return service, creds_b64

    except (pyt.error.PyYouTubeException, ValueError, AttributeError) as error:
        if utils.history:
            utils.history.critical('(%s) %s', error, instance_fail_message)
        raise YouTubeServiceError(f'{instance_fail_message}: {error}')
