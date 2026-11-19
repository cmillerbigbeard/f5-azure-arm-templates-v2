# BIG-IP HA pair on Azure: 2 NICs (management + internal), no public IP addresses

Deploys a two-unit BIG-IP high-availability pair with Cloud Failover Extension into an **existing** Azure virtual network, with **no public IP addresses** on the BIG-IPs (no bastion, load balancer, example application or virtual server). BYOL licensing.

**Start here: [deployment guide](examples/failover/README-2nic-internal.md).** It covers prerequisites (including the outbound access the BIG-IPs need), every template parameter, the portal button and the Azure CLI steps, how to check that the pair formed, and what was and was not tested.

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fcmillerbigbeard%2Ff5-azure-arm-templates-v2%2Fazure-2nic-internal-offline%2Fexamples%2Ffailover%2Fazuredeploy-existing-network-2nic-internal.json)

Read the guide before deploying: the button only opens the portal form, and the template needs an existing network with outbound access from the management subnet.

**No internet access at all?** Section 13 of the guide covers an offline variant: the BIG-IPs install their automation packages from a web server inside your network, and two scripts in [examples/failover/offline](examples/failover/offline) license the units by hand and form the pair.

**Cannot create roles in your subscription?** Section 14 of the guide covers deploying with a managed identity that someone else created beforehand.

## What is in this repository

| Path | What it is |
|---|---|
| `examples/failover/azuredeploy-existing-network-2nic-internal.json` | The template |
| `examples/failover/README-2nic-internal.md` | The deployment guide |
| `examples/failover/bigip-configurations/` | The BIG-IP onboarding configurations the template loads at first boot (BYOL, one per unit), and the install-only configuration for the offline variant |
| `examples/failover/offline/` | The two scripts for the offline variant |
| `examples/modules/` | The three linked templates (`access`, `bigip-standalone`, `dag`) that the template deploys |

## Where this comes from

This is derived from F5's `failover` solution in [F5Networks/f5-azure-arm-templates-v2](https://github.com/F5Networks/f5-azure-arm-templates-v2), reduced to two NICs, with the public IP addresses, bastion, load balancer and example application removed, and with the storage accounts created as `StorageV2`. F5's original templates, including the 3-NIC and autoscale solutions, are in F5's repository and are not part of this one. The guide's section "What differs from F5's template" lists every change.

F5 does not provide technical support for this derived template.

---

### Copyright

Copyright 2014-2023 F5 Networks Inc.

### License

#### Apache V2.0

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License. You may obtain a copy of the
License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations
under the License.

#### Contributor License Agreement

Individuals or business entities who contribute to this project must have
completed and submitted the F5 Contributor License Agreement.