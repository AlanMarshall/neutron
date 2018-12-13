# Copyright 2018 Red Hat, Inc.
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

import errno

from oslo_utils import uuidutils
import pyroute2
from pyroute2.netlink import rtnl

from neutron.agent.linux import tc_lib
from neutron.privileged.agent.linux import ip_lib as priv_ip_lib
from neutron.privileged.agent.linux import tc_lib as priv_tc_lib
from neutron.tests.functional import base as functional_base


class TcQdiscTestCase(functional_base.BaseSudoTestCase):

    def setUp(self):
        super(TcQdiscTestCase, self).setUp()
        self.namespace = 'ns_test-' + uuidutils.generate_uuid()
        priv_ip_lib.create_netns(self.namespace)
        self.addCleanup(self._remove_ns, self.namespace)
        self.device = 'int_dummy'
        priv_ip_lib.create_interface(self.device, self.namespace, 'dummy')

    def _remove_ns(self, namespace):
        priv_ip_lib.remove_netns(namespace)

    def test_add_tc_qdisc_htb(self):
        priv_tc_lib.add_tc_qdisc(
            self.device, parent=rtnl.TC_H_ROOT, kind='htb', handle='5:',
            namespace=self.namespace)
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(1, len(qdiscs))
        self.assertEqual(rtnl.TC_H_ROOT, qdiscs[0]['parent'])
        self.assertEqual(0x50000, qdiscs[0]['handle'])
        self.assertEqual('htb', tc_lib._get_attr(qdiscs[0], 'TCA_KIND'))

        priv_tc_lib.delete_tc_qdisc(self.device, rtnl.TC_H_ROOT,
                                    namespace=self.namespace)
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(0, len(qdiscs))

    def test_add_tc_qdisc_htb_no_handle(self):
        priv_tc_lib.add_tc_qdisc(
            self.device, parent=rtnl.TC_H_ROOT, kind='htb',
            namespace=self.namespace)
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(1, len(qdiscs))
        self.assertEqual(rtnl.TC_H_ROOT, qdiscs[0]['parent'])
        self.assertEqual(0, qdiscs[0]['handle'] & 0xFFFF)
        self.assertEqual('htb', tc_lib._get_attr(qdiscs[0], 'TCA_KIND'))

        priv_tc_lib.delete_tc_qdisc(self.device, parent=rtnl.TC_H_ROOT,
                                    namespace=self.namespace)
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(0, len(qdiscs))

    def test_add_tc_qdisc_tbf(self):
        burst = 192000
        rate = 320000
        latency = 50000
        priv_tc_lib.add_tc_qdisc(
            self.device, parent=rtnl.TC_H_ROOT, kind='tbf', burst=burst,
            rate=rate, latency=latency, namespace=self.namespace)
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(1, len(qdiscs))
        self.assertEqual(rtnl.TC_H_ROOT, qdiscs[0]['parent'])
        self.assertEqual('tbf', tc_lib._get_attr(qdiscs[0], 'TCA_KIND'))
        tca_options = tc_lib._get_attr(qdiscs[0], 'TCA_OPTIONS')
        tca_tbf_parms = tc_lib._get_attr(tca_options, 'TCA_TBF_PARMS')
        self.assertEqual(rate, tca_tbf_parms['rate'])
        self.assertEqual(burst, tc_lib._calc_burst(tca_tbf_parms['rate'],
                                                   tca_tbf_parms['buffer']))
        self.assertEqual(latency, tc_lib._calc_latency_ms(
            tca_tbf_parms['limit'], burst, tca_tbf_parms['rate']) * 1000)

        priv_tc_lib.delete_tc_qdisc(self.device, parent=rtnl.TC_H_ROOT,
                                    namespace=self.namespace)
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(0, len(qdiscs))

    def test_add_tc_qdisc_ingress(self):
        priv_tc_lib.add_tc_qdisc(self.device, kind='ingress',
                                 namespace=self.namespace)
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(1, len(qdiscs))
        self.assertEqual('ingress', tc_lib._get_attr(qdiscs[0], 'TCA_KIND'))
        self.assertEqual(rtnl.TC_H_INGRESS, qdiscs[0]['parent'])
        self.assertEqual(0xffff0000, qdiscs[0]['handle'])

        priv_tc_lib.delete_tc_qdisc(self.device, kind='ingress',
                                    namespace=self.namespace)
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(0, len(qdiscs))

    def test_delete_tc_qdisc_no_device(self):
        self.assertRaises(
            priv_ip_lib.NetworkInterfaceNotFound, priv_tc_lib.delete_tc_qdisc,
            'other_device', rtnl.TC_H_ROOT, namespace=self.namespace)

    def test_delete_tc_qdisc_no_device_no_exception(self):
        self.assertIsNone(priv_tc_lib.delete_tc_qdisc(
            'other_device', rtnl.TC_H_ROOT, namespace=self.namespace,
            raise_interface_not_found=False))

    def test_delete_tc_qdisc_no_qdisc(self):
        self.assertRaises(
            pyroute2.NetlinkError, priv_tc_lib.delete_tc_qdisc,
            self.device, rtnl.TC_H_ROOT, namespace=self.namespace)

    def test_delete_tc_qdisc_no_qdisc_no_exception(self):
        self.assertEqual(2, priv_tc_lib.delete_tc_qdisc(
            self.device, rtnl.TC_H_ROOT, namespace=self.namespace,
            raise_qdisc_not_found=False))

    def test_delete_tc_qdisc_ingress_twice(self):
        priv_tc_lib.add_tc_qdisc(self.device, kind='ingress',
                                 namespace=self.namespace)
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(1, len(qdiscs))
        self.assertEqual('ingress', tc_lib._get_attr(qdiscs[0], 'TCA_KIND'))
        self.assertIsNone(
            priv_tc_lib.delete_tc_qdisc(self.device, kind='ingress',
                                        namespace=self.namespace))
        qdiscs = priv_tc_lib.list_tc_qdiscs(self.device,
                                            namespace=self.namespace)
        self.assertEqual(0, len(qdiscs))
        self.assertEqual(
            errno.EINVAL,
            priv_tc_lib.delete_tc_qdisc(self.device, kind='ingress',
                                        namespace=self.namespace,
                                        raise_qdisc_not_found=False))


class TcPolicyClassTestCase(functional_base.BaseSudoTestCase):

    def setUp(self):
        super(TcPolicyClassTestCase, self).setUp()
        self.namespace = 'ns_test-' + uuidutils.generate_uuid()
        priv_ip_lib.create_netns(self.namespace)
        self.addCleanup(self._remove_ns, self.namespace)
        self.device = 'int_dummy'
        priv_ip_lib.create_interface(self.device, self.namespace, 'dummy')

    def _remove_ns(self, namespace):
        priv_ip_lib.remove_netns(namespace)

    def test_add_tc_policy_class_htb(self):
        priv_tc_lib.add_tc_qdisc(
            self.device, kind='htb', parent=rtnl.TC_H_ROOT, handle='1:',
            namespace=self.namespace)
        classes = {'1:1': {'rate': 10000, 'ceil': 20000, 'burst': 1500},
                   '1:3': {'rate': 20000, 'ceil': 50000, 'burst': 1600},
                   '1:5': {'rate': 30000, 'ceil': 90000, 'burst': 1700},
                   '1:7': {'rate': 35001, 'ceil': 90000, 'burst': 1701}}
        for classid, rates in classes.items():
            priv_tc_lib.add_tc_policy_class(
                self.device, '1:', classid, 'htb', namespace=self.namespace,
                **rates)

        tc_classes = priv_tc_lib.list_tc_policy_classes(
            self.device, namespace=self.namespace)
        self.assertEqual(len(classes), len(tc_classes))
        for tc_class in tc_classes:
            handle = tc_lib._handle_from_hex_to_string(tc_class['handle'])
            tca_options = tc_lib._get_attr(tc_class, 'TCA_OPTIONS')
            tca_htb_params = tc_lib._get_attr(tca_options, 'TCA_HTB_PARMS')
            self.assertEqual(classes[handle]['rate'], tca_htb_params['rate'])
            self.assertEqual(classes[handle]['ceil'], tca_htb_params['ceil'])
            burst = tc_lib._calc_burst(classes[handle]['rate'],
                                       tca_htb_params['buffer'])
            self.assertEqual(classes[handle]['burst'], burst)
