# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from __future__ import print_function
from cloudpulse.operator.ansible.ansible_runner import ansible_runner
from cloudpulse.operator.ansible.openstack_node_info_reader import \
    openstack_node_info_reader
from cloudpulse.scenario import base
from oslo_config import cfg
import re

TESTS_OPTS = [
    cfg.StrOpt('operator_setup_file',
               default='/etc/cloudpulse/openstack_config.yaml',
               help='Setup File for the operator'),
    cfg.BoolOpt('containerized',
                default=True,
                help='enable if the processes are running as containers'),
    cfg.StrOpt('rabbit_container',
               default='rabbitmq_v1',
               help='name of the rabitmq container'),
    cfg.StrOpt('galera_container',
               default='mariadb_v1',
               help='name of the galera cluster container'),

]

PERIODIC_TESTS_OPTS = [
    cfg.IntOpt('rabbitmq_check',
               default=0,
               help='The rabbitmq periodic check'),
    cfg.IntOpt('galera_check',
               default=0,
               help='The galera periodic check')
]

CONF = cfg.CONF

operator_test_group = cfg.OptGroup(name='operator_test',
                                   title='Options for the Operators')
CONF.register_group(operator_test_group)
CONF.register_opts(TESTS_OPTS, operator_test_group)

periodic_test_group = cfg.OptGroup(name='periodic_tests',
                                   title='Periodic tests to be run')
CONF.register_opts(PERIODIC_TESTS_OPTS, periodic_test_group)


class operator_scenario(base.Scenario):

    def load(self):
        self.os_node_info_obj = openstack_node_info_reader(
            cfg.CONF.operator_test.operator_setup_file)
        openstack_node_list = self.os_node_info_obj.get_host_list()
        self.ans_runner = ansible_runner(openstack_node_list)
        inventory = self.ans_runner.init_ansible_inventory(openstack_node_list)
        self.ans_runner.set_ansible_inventory(inventory)

    @base.scenario(admin_only=False, operator=True)
    def rabbitmq_check(self):
        self.load()
        cmd = "rabbitmqctl cluster_status -q"

        is_containerized = cfg.CONF.operator_test.containerized
        if is_containerized:
            rabbit_container = cfg.CONF.operator_test.rabbit_container
            cmd = ("docker exec %s %s" % (rabbit_container, cmd))

        out = self.ans_runner.execute(cmd)
        res, output = self.ans_runner.validate_results(out)

        node_status = res['contacted'][res['contacted'].keys()[0]]['stdout']
        node_status_string = node_status.replace('\n', '')
        mathobj = re.search(
            r'running_nodes,(.*?)}', node_status_string, re.M | re.I)
        nodes = mathobj.group(1)

        if res['status'] is 'PASS':
            return (200, "Active Nodes : %s" % nodes,
                    ['RabbitMQ-server Running'])
        else:
            return (404, ("RabbitMQ-server test failed :%s" %
                          res['status_message']), [])

    @base.scenario(admin_only=False, operator=True)
    def galera_check(self):
        self.load()
        galera = self.os_node_info_obj.get_galera_details()

        cmd = (r"mysql -u %s -e 'SHOW STATUS;'|grep wsrep_incoming_addresses" %
               (galera['username']))

        is_containerized = cfg.CONF.operator_test.containerized
        if is_containerized:
            galera_container = cfg.CONF.operator_test.galera_container
            cmd = ("docker exec %s %s" % (galera_container, cmd))

        out = self.ans_runner.execute(cmd)
        results, failed_hosts = self.ans_runner.validate_results(out)

        galera_status = results['contacted'][
            results['contacted'].keys()[0]]['stdout']
        galera_status_string = galera_status.replace('\n', '')
        mathobj = re.search(r'wsrep_incoming_addresses\s+(.*?)$',
                            galera_status_string, re.M | re.I)
        nodes = mathobj.group(1)

        if results['status'] is 'PASS':
            return (200, "Active Nodes : %s" % nodes,
                    ['Galera Cluster Test Passed'])
        else:
            return (404, ("Galera Cluster Test Failed: %s" %
                          results['status_message']), [])
