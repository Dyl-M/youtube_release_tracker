# -*- coding: utf-8 -*-

import ast
import json
import os
import pyyoutube as pyt
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

"""File Information
@file_name: _sandbox.py
@author: Dylan "dyl-m" Monfret
To test things / backup functions.
"""

"Functions"


def create_service():
    """Create a GCP service for YouTube API V3.
    Mostly inspired by this: https://learndataanalysis.org/google-py-file-source-code/
    :return service:
    """
    oauth_file = '../tokens/oauth.json'  # OAUTH 2.0 ID path
    scopes = ['https://www.googleapis.com/auth/youtube', 'https://www.googleapis.com/auth/youtube.force-ssl']
    instance_fail_message = 'Failed to create service instance for YouTube'
    cred = None

    if os.path.exists('../tokens/credentials.json'):
        cred = Credentials.from_authorized_user_file('../tokens/credentials.json')  # Retrieve credentials

    if not cred or not cred.valid:  # Cover outdated or non-existant credentials
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())

        else:
            # Create the authentification Flow from 'oauth_file' and then run authentication process
            flow = InstalledAppFlow.from_client_secrets_file(oauth_file, scopes)
            cred = flow.run_local_server()

        with open('../tokens/credentials.json', 'w') as cred_file:  # Save credentials as a JSON file
            json.dump(ast.literal_eval(cred.to_json()), cred_file, ensure_ascii=False, indent=4)

    try:
        service = pyt.Client(access_token=cred.token)
        print('YouTube service created successfully.')

        return service

    except Exception as error:  # skipcq: PYL-W0703 - No known errors at the moment.
        print(f'{error}: {instance_fail_message}')
        sys.exit()


"Main"

if __name__ == '__main__':
    my_service = create_service()
    print(my_service.playlists.list(mine=True, max_results=50).items)
