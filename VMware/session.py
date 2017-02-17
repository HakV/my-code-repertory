# Copyright 2016 Beijing Huron Technology Co.Ltd.
#
# Authors: Fan Guiju <fanguiju@hihuron.com>
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import six
from urlparse import urlparse
import webob

from oslo_log import log as logging
from oslo_vmware import api
from oslo_vmware import exceptions as vexc

from egis.i18n import _LE


LOG = logging.getLogger(__name__)

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
    except vexc.VimFaultException as err:
        LOG.exception(_LE("Failed to create the session of vmware, "
                          "detailed error as %s"),
                      six.text_type(err))
        raise vexc.VimFaultException()
    except Exception as err:
        LOG.exception(_LE("Failed to create the session of vmware, "
                          "detailed error as %s"),
                      six.text_type(err))
        raise webob.exc.HTTPInternalServerError()
