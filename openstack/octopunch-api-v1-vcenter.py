# Copyright 2012-2013 Beijing Huron Technology Co.Ltd.
#
# Author: Fan Guiju <fanguiju@hihuron.com>
#                                                                                           
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See
# the
# License for the specific language governing permissions and limitations
# under the License.
import uuid as uuid_generator

import webob
from webob import exc

from octopunch import exception
from octopunch.api.openstack import wsgi
from octopunch.vsphere.vcenter import api 
from octopunch.i18n import _LE
from oslo_log import log as logging

LOG = logging.getLogger(__file__)

class VcenterController(wsgi.Controller):

    def __init__(self, ext_mgr):
        self.ext_mgr = ext_mgr
        self.vcenter_api = api.API()
        super(VcenterController, self).__init__()

    @wsgi.serializers()
    def index(self, req):
        """Show all vcenter list."""
        context = req.environ['octopunch.context']
        vcenters = self.vcenter_api.vcenter_list(context)
        return {'vcenters':vcenters}

    @wsgi.serializers()
    def show(self, req, id):
        """show a vcenter."""

        context = req.environ['octopunch.context']
        vcenter = self.vcenter_api.vcenter_get(context, id)
        return {'vcenter':vcenter}

    @wsgi.serializers()
    def create(self, req, body):
        """Create a vcenter."""
        context = req.environ['octopunch.context']
        
        uuid = str(uuid_generator.uuid4())

        vcs_ip = body.get('vcs_ip')
        username = body.get('username')
        password = body.get('password')

        if vcs_ip is None or vcs_ip == '':
            raise exc.HTTPUnprocessableEntity()
        if username is None or username =='':
            raise exc.HTTPUnprocessableEntity()
        if password is None or password =='':
            raise exc.HTTPUnprocessableEntity()

        valid_create_keys = ('vc_value',
                             'name',
                             'vcs_ip',
                             'username',
                             'password')

        create_dict = {'uuid':uuid}
        for key in valid_create_keys:
            if key in body:
                create_dict[key] = body[key]

        vcenter = self.vcenter_api.vcenter_create(context, create_dict)
        return {'vcenter':vcenter}

    @wsgi.serializers()
    def update(self, req, id, body=None):
        """Update the vcenter."""

        import pdb
        pdb.set_trace()
        context = req.environ['octopunch.context']

        if body is None or body == '':
            raise exc.HTTPUnprocessableEntity()

        valid_create_keys = ('vc_value',
                             'name',
                             'vcs_ip',
                             'username',
                             'password')

        update_dict = {}

        for key in valid_create_keys:
            if key in body:
                update_dict[key] = body[key]
        
        try:
           vcenter = self.vcenter_api.vcenter_update(context, id,
                                                update_dict) 
        except exception.NotFound:
            raise exc.HTTPNotFound

        return {'vcenter':vcenter}

    @wsgi.serializers()
    def delete(self, req, id):
        """Delete the vcenter."""
        context = req.environ['octopunch.context']
        LOG.info(_LE("Delete vcenter with id %s"), id,
                 context=context)
        try:
            self.vcenter_api.vcenter_delete(context, id)
            return webob.Response(status_int=202)
        except exception.NotFound:
            raise exc.HTTPNotFound


def create_resource(ext_mgr):
    """Vcenter resource factory method."""
    return wsgi.Resource(VcenterController(ext_mgr))
