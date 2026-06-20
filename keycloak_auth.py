"""
OAuth / OIDC authentication helper for the Jira connector.
Implements Client Credentials flow and RFC 8693 Token Exchange.
"""
import logging
import time
from typing import Optional
import httpx
from crew_jira_connector.config import get_settings

logger = logging.getLogger(__name__)


class ConnectorAuth:
    def __init__(self):
        self.settings = get_settings()
        self.token_url = self.settings.keycloak_token_url
        self.client_id = self.settings.keycloak_client_id
        self.client_secret = self.settings.keycloak_client_secret
        
        # In-memory cache for the connector's own service token
        self._service_token: Optional[str] = None
        self._service_token_expiry: float = 0.0

    def get_service_token(self) -> Optional[str]:
        """
        Get the connector's own service account token using Client Credentials flow.
        Caches the token in memory based on its expiry time.
        """
        if not self.token_url or not self.client_id:
            logger.warning("OIDC authentication config missing. Proceeding unauthenticated.")
            return None

        # Check if cached token is still valid (with 30-second buffer)
        now = time.time()
        if self._service_token and now < self._service_token_expiry - 30:
            return self._service_token

        try:
            logger.info("Requesting service account token via Client Credentials flow")
            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
            }
            if self.client_secret:
                data["client_secret"] = self.client_secret

            response = httpx.post(self.token_url, data=data, timeout=10.0)
            response.raise_for_status()
            res_data = response.json()
            
            self._service_token = res_data.get("access_token")
            expires_in = res_data.get("expires_in", 300)
            self._service_token_expiry = now + expires_in
            
            return self._service_token
        except Exception as e:
            logger.exception("Failed to fetch service account token: %s", e)
            return None

    def get_user_token(self, user_email: str) -> Optional[str]:
        """
        Perform Token Exchange (RFC 8693) to swap the service account token for a user token.
        Returns None if token exchange is not configured or fails.
        """
        if not self.token_url or not self.client_id:
            return None

        subject_token = self.get_service_token()
        if not subject_token:
            logger.warning("Cannot exchange token: service token is unavailable")
            return None

        try:
            logger.info("Exchanging service token for user token (subject: %s)", user_email)
            data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "client_id": self.client_id,
                "subject_token": subject_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "requested_subject": user_email,
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
            }
            if self.client_secret:
                data["client_secret"] = self.client_secret

            response = httpx.post(self.token_url, data=data, timeout=10.0)
            
            # If identity provider returns 400 (e.g. user not found), return None to fallback
            if response.status_code == 400:
                logger.warning("Token Exchange failed: user %s might not exist in Identity Provider", user_email)
                return None
                
            response.raise_for_status()
            res_data = response.json()
            return res_data.get("access_token")
        except Exception as e:
            logger.warning("Token Exchange failed for %s: %s", user_email, e)
            return None
