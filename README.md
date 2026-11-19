# BIG-IP HA pair on Azure: 2 NICs, no public IPs, built for networks with no internet access

Deploys a two-unit BIG-IP high-availability pair with Cloud Failover Extension into an **existing** Azure virtual network. Each unit has two network interfaces (management and internal) and **no public IP address**; there is no bastion, load balancer, example application or virtual server. BYOL licensing.

**This branch assumes the BIG-IPs have no route to the internet.** They install their automation packages from a web server inside your network, and you license them by hand. If your BIG-IPs *can* reach the internet, see [If the BIG-IPs can reach the internet](#if-the-big-ips-can-reach-the-internet) below.

**Full instructions: [deployment guide, section 13](examples/failover/README-2nic-internal.md#13-deploying-with-no-internet-access-at-all-offline-variant).** The rest of the guide covers every template parameter, the checks that the pair formed, and troubleshooting.

## The three steps

1. **Host five files on a web server your management subnet can reach** over HTTP(S). A UNC or file-share path will not work, because the BIG-IP downloads with `curl`. The files, their download links and SHA-256 values are in [guide section 13.2](examples/failover/README-2nic-internal.md#132-files-to-host-internally). Also copy [runtime-init-conf-2nic-installonly.yaml](examples/failover/bigip-configurations/runtime-init-conf-2nic-installonly.yaml) to the server and edit its three `extensionUrl` lines so each one is the full URL of that file on your server (replace the whole `https://<INTERNAL-HOST>/f5-files` prefix; use `http://` if that is what your server serves).
2. **Deploy the template** (button below, or the Azure CLI in the guide), setting these parameters in addition to the usual ones:

   | Parameter | Value |
   |---|---|
   | `bigIpRuntimeInitPackageUrl` | the URL of `f5-bigip-runtime-init-2.0.3-1.gz.run` on your server |
   | `bigIpRuntimeInitConfig01` and `bigIpRuntimeInitConfig02` | the URL of your edited install-only configuration (the same file for both units) |
   | `bigIpRuntimeInitKeyUrl` | `--key https://<your server>/gpg.key --skip-toolchain-metadata-sync` |
   | `bigIpImage` | `f5-networks:f5-big-ip-byol:f5-big-all-2slot-byol:17.5.111000` (see "What has and has not been tested") |

   Each unit reads the `admin` password from Azure Key Vault at onboarding, so that vault must be reachable from the management subnet through a service or private endpoint (guide sections 13.3 and 14).
3. **License the units and form the pair** with the two scripts in [examples/failover/offline](examples/failover/offline), run from a machine that can reach both management addresses over SSH. `stage2-license.py` prints each unit's dossier; you paste it into F5's activation page (https://activate.f5.com/license/dossier.jsp) from any computer with internet access and paste the licence text back. `stage2-apply.py` then applies the configuration and forms the pair. The BIG-IPs themselves never contact F5.

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fcmillerbigbeard%2Ff5-azure-arm-templates-v2%2Fazure-2nic-internal-offline%2Fexamples%2Ffailover%2Fazuredeploy-existing-network-2nic-internal.json)

The button opens the Azure portal's custom deployment form for this template. Enter the parameters above in the form. The deployment only installs the units; steps 1 and 3 are outside the template.

## If the BIG-IPs can reach the internet

Use the same template and leave the four offline parameters empty. The units then download their packages and activate their licence themselves, which needs outbound access **from the management subnet** (not only the internal one) to `raw.githubusercontent.com`, `cdn.f5.com`, `f5-cft.s3.amazonaws.com` and `activate.f5.com`. See guide sections 2 to 12.

**Cannot create roles in your subscription?** Guide section 14 covers deploying with a managed identity that someone else created beforehand.

## What has and has not been tested

This was built and tested by one person in a lab, not by F5. Treat it as a reference, and run your own tests.

- **Tested:** BIG-IP 17.5.1.11, with Declarative Onboarding 1.44.0, AS3 3.51.0 and Cloud Failover Extension 2.1.2. With no internet access on either subnet, the offline route installed both units, licensed them and formed a pair: both devices listed, `In Sync`, one `ACTIVE` and one `STANDBY`.
- **Limits of the offline route:** Cloud Failover Extension cannot move Azure addresses without a route to `management.azure.com`, so a failover will not move any address until one exists. Licensing is manual. Remote REST login as `admin` returned `401` on units set up this way (cause not found), so the scripts work over SSH.
- **Not verified:** BIG-IP 21.1. One lab deployment of `21.1.004000` failed during onboarding and the cause was not found, so 21.1 is **not verified**. The template's default `bigIpImage` is still `21.1.004000`; set it explicitly as shown above.
- **Not verified:** clicking the Deploy to Azure button and completing the portal form. Every deployment used the Azure CLI with the same template.
- **Not verified:** client traffic through a virtual server during a failover, other VM sizes or regions, and availability zones.

The guide's sections 11 and 12 list every result and every failure in detail.

## Where this comes from

This is a personal fork derived from the `failover` solution in [F5Networks/f5-azure-arm-templates-v2](https://github.com/F5Networks/f5-azure-arm-templates-v2), reduced to two NICs, with the public IP addresses, bastion, load balancer and example application removed, and with the storage accounts created as `StorageV2`. It is not an F5 product and F5 does not support it. F5's original templates, including the 3-NIC and autoscale solutions, are in F5's repository and are not part of this branch. The guide's section "What differs from F5's template" lists every change.

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