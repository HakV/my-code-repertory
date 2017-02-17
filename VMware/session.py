from urlparse import urlparse

from oslo_vmware import api
from oslo_vmware import exceptions as vexc


API_RETRY_COUNT = 2
TASK_POLL_INNTERVAL = 3


def get_session(auth_url, username, password):
    """Get vmware session object."""
    try:
        vmware_url = urlparse(auth_url)
        session = api.VMwareAPISession(
            host=vmware_url.hostname,
            server_username=username,
            server_password=password,
            api_retry_count=API_RETRY_COUNT,
            task_poll_interval=TASK_POLL_INNTERVAL,
            port=vmware_url.port)
        return session
    except vexc.VimFaultException:
        raise
    except Exception as err:
        raise
