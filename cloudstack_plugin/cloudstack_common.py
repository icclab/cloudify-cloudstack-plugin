########
# Copyright (c) 2014 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# * See the License for the specific language governing permissions and
# * limitations under the License.
import os
import json

from cloudify import context
from cloudify.exceptions import NonRecoverableError

from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver
import libcloud.security


# properties
USE_EXTERNAL_RESOURCE_PROPERTY = 'use_external_resource'

# runtime properties
CLOUDSTACK_ID_PROPERTY = 'external_id'  # resource's cloudstack id
CLOUDSTACK_TYPE_PROPERTY = 'external_type'  # resource's cloudstack type
CLOUDSTACK_NAME_PROPERTY = 'external_name'  # resource's cloudstack name

# runtime properties which all types use
COMMON_RUNTIME_PROPERTIES_KEYS = [CLOUDSTACK_ID_PROPERTY,
                                  CLOUDSTACK_TYPE_PROPERTY,
                                  CLOUDSTACK_NAME_PROPERTY]


class ProviderContext(object):

    def __init__(self, provider_context):
        self._provider_context = provider_context or {}
        self._resources = self._provider_context.get('resources', {})

    @property
    def agents_keypair(self):
        return self._resources.get('agents_keypair')

    @property
    def agents_security_group(self):
        return self._resources.get('agents_security_group')

    @property
    def ext_network(self):
        return self._resources.get('ext_network')

    @property
    def floating_ip(self):
        return self._resources.get('floating_ip')

    @property
    def int_network(self):
        return self._resources.get('int_network')

    @property
    def management_keypair(self):
        return self._resources.get('management_keypair')

    @property
    def management_security_group(self):
        return self._resources.get('management_security_group')

    @property
    def management_server(self):
        return self._resources.get('management_server')

    @property
    def router(self):
        return self._resources.get('router')

    @property
    def subnet(self):
        return self._resources.get('subnet')

    def __repr__(self):
        info = json.dumps(self._provider_context)
        return '<' + self.__class__.__name__ + ' ' + info + '>'


def provider(ctx):
    return ProviderContext(ctx.provider_context)


def _get_auth_from_context(ctx):

    config = Config().get()
    secret_probe = config.get(['cs_api_secret'][0], None)

    # TODO a hack to distinguish auth code-path (mgr blueprint vs mgr.json)
    if secret_probe is None:

        if ctx.type == context.NODE_INSTANCE:
            config = ctx.node.properties.get('cloudstack_config')
        elif ctx.type == context.RELATIONSHIP_INSTANCE:
            config = ctx.source.node.properties.get('cloudstack_config')
            if not config:
                config = ctx.target.node.properties.get('cloudstack_config')
        else:
            config = Config().get()

    return config


def get_cloud_driver(ctx):
    auth_config = _get_auth_from_context(ctx)
    api_key = auth_config['cs_api_key']
    api_secret_key = auth_config['cs_api_secret']
    api_url = auth_config['cs_api_url']
    driver = get_driver(Provider.CLOUDSTACK)
    libcloud.security.VERIFY_SSL_CERT = False
    return driver(key=api_key, secret=api_secret_key, url=api_url)


class Config(object):

    CLOUDSTACK_CONFIG_PATH_ENV_VAR = 'CLOUDSTACK_CONFIG_PATH'
    CLOUDSTACK_CONFIG_PATH_DEFAULT_PATH = '~/cloudstack_config.json'

    def get(self):
        static_config = self._build_config_from_env_variables()
        env_name = self.CLOUDSTACK_CONFIG_PATH_ENV_VAR
        default_location_tpl = self.CLOUDSTACK_CONFIG_PATH_DEFAULT_PATH
        default_location = os.path.expanduser(default_location_tpl)
        config_path = os.getenv(env_name, default_location)
        try:
            with open(config_path) as f:
                Config.update_config(static_config, json.loads(f.read()))
        except IOError:
            pass
        return static_config

    @staticmethod
    def _build_config_from_env_variables():
        cfg = dict()

        def take_env_var_if_exists(cfg_key, env_var):
            if env_var in os.environ:
                cfg[cfg_key] = os.environ[env_var]

        take_env_var_if_exists('cs_api_key', 'CS_API_KEY')
        take_env_var_if_exists('cs_api_secret', 'CS_API_SECRET')
        take_env_var_if_exists('cs_api_url', 'CS_API_URL')

        return cfg

    @staticmethod
    def update_config(overridden_cfg, overriding_cfg):
        """ this method is like dict.update() only that it doesn't override
        with (or set new) empty values (e.g. empty string) """
        for k, v in overriding_cfg.iteritems():
            if v:
                overridden_cfg[k] = v


def get_nic_by_node_and_network_id(ctx, cloud_driver, node, network_id):

    nics = [nic for nic in cloud_driver.ex_list_nics(node)
            if network_id == nic.network_id]

    if not nics:
        ctx.logger.debug('could not find nic by node_id {0} and network_id {1}'
                         .format(node.id, network_id))
        return None

    return nics[0]


def get_resource_id(ctx, type_name):
    if ctx.node.properties['resource_id']:
        return ctx.node.properties['resource_id']
    return "{0}_{1}_{2}".format(type_name, ctx.deployment.id, ctx.instance.id)


def get_location(cloud_driver, location_name):
    locations = [location for location in cloud_driver
                 .list_locations() if location.name == location_name]
    if locations.__len__() == 0:
        raise NonRecoverableError("Zone/Location: {0} cannot be found!"
                                  .format(location_name))
    return locations[0]


def get_cloudstack_ids_of_connected_nodes_by_cloudstack_type(ctx, type_name):
    type_caps = [caps for caps in ctx.capabilities.get_all().values()
                 if caps.get(CLOUDSTACK_TYPE_PROPERTY) == type_name]
    return [cap[CLOUDSTACK_ID_PROPERTY] for cap in type_caps]


def delete_runtime_properties(ctx, runtime_properties_keys):
    for runtime_prop_key in runtime_properties_keys:
        if runtime_prop_key in ctx.instance.runtime_properties:
            del ctx.instance.runtime_properties[runtime_prop_key]
