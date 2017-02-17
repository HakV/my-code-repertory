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
import webob

from oslo_log import log as logging
from oslo_vmware import exceptions as vexc
from oslo_vmware import vim_util

from egis import exception
from egis.i18n import _LE
from egis.virt.base import api as core_api
from egis.virt.vmware import session


LOG = logging.getLogger(__name__)

MAX_NUMBER_OBJECTS_RETURN = 100


class DataCollector(object):
    def __init__(self, context, vmware_connect_id):
        self.core_api = core_api.API()

        try:
            vmware_connect_info = self.core_api.hyper_connection_get(
                context,
                hyper_connection_id=vmware_connect_id)
        except exception.NotFound as err:
            LOG.exception(
                _LE("Hyper connection %(id)s not found, "
                    "detailed error as %(err)s"),
                {'id': vmware_connect_id, 'err': six.text_type(err)})
            raise webob.exc.HTTPNotFound()

        self.session = session.get_session(vmware_connect_info.auth_url,
                                           vmware_connect_info.username,
                                           vmware_connect_info.password)

    def managed_object_get(self, managed_object_type):
        """Get managed object of vsphere."""
        LOG.debug("Get vmware manage object %s", managed_object_type)

        try:
            # param: maximum number of objects that should be returned in a
            #        single call = 100
            managed_object = self.session.invoke_api(
                vim_util,
                'get_objects',
                self.session.vim,
                managed_object_type,
                MAX_NUMBER_OBJECTS_RETURN)
            return managed_object
        except vexc.ManagedObjectNotFoundException as err:
            LOG.exception(
                _LE("Vmware manage object %(mo) not found, "
                    "datailed error as %(err)s"),
                {'mo': managed_object_type, 'err': six.text_type(err)})
            raise vexc.ManagedObjectNotFoundException()

    def manager_properties_dict_get(self, managed_subobject, propertie):
        """Get the properties dict of manager object"""

        LOG.debug("Get the propertie %(propertie)s of vmware "
                  "manage subobject %(managed_subobject)s.",
                  {'propertie': propertie,
                   'managed_subobject': managed_subobject})

        try:
            manager_properties_dict = self.session.invoke_api(
                vim_util,
                'get_object_properties_dict',
                self.session.vim,
                managed_subobject,
                propertie)
            return manager_properties_dict
        except Exception as err:
            LOG.exception(
                _LE("Failed to get the propertie %(propertie)s of vmware "
                    "manage subobject %(managed_subobject)s, "
                    "detailed error as %(err)s"),
                {'propertie': propertie,
                 'managed_subobject': managed_subobject,
                 'err': six.text_type(err)})
