import hashlib

from rest_framework.throttling import SimpleRateThrottle


class _IPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class CodeSendIPThrottle(_IPThrottle):
    """Limits code emails requested from one IP address."""

    scope = "code_send_ip"


class CodeSendEmailThrottle(SimpleRateThrottle):
    """Limits code emails sent to one address, whichever IP asks.

    Keyed by a hash of the submitted address, so unknown addresses are limited
    exactly like real ones and the cache never holds email addresses.
    """

    scope = "code_send_email"

    def get_cache_key(self, request, view):
        email = request.data.get("email") if hasattr(request.data, "get") else None
        if not isinstance(email, str) or not email.strip():
            return None
        ident = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}


class CodeVerifyThrottle(_IPThrottle):
    """Limits code guesses from one IP address across all accounts."""

    scope = "code_verify"
