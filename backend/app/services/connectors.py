"""Connector stubs for phase-C real integrations."""

class ConnectorNotConfigured(Exception):
    pass


def fetch_google_calendar():
    raise ConnectorNotConfigured("Google Calendar connector not configured")


def fetch_jobber():
    raise ConnectorNotConfigured("Jobber connector not configured")


def fetch_immich():
    raise ConnectorNotConfigured("Immich connector not configured")


def fetch_paperless():
    raise ConnectorNotConfigured("Paperless connector not configured")
