from __future__ import annotations

from typing import List, Tuple, Set
from collections.abc import Generator
from datetime import datetime 
from alibabacloud_cdn20180510.client import Client as Cdn20180510Client
from alibabacloud_live20161101.client import Client as live20161101Client
from alibabacloud_cas20200407.client import Client as cas20200407Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_cdn20180510 import models as cdn_20180510_models
from alibabacloud_live20161101 import models as live_20161101_models
from alibabacloud_cas20200407 import models as cas_20200407_models

import logging

log = logging.getLogger(__name__)

class Aliyun:
    def __init__(self, access_key_id, access_key_secret) -> None:
        self._cdn_client = Cdn20180510Client(
            open_api_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                # Endpoint 请参考 https://api.aliyun.com/product/Cdn
                endpoint="cdn.aliyuncs.com"
            )
        )
        self._live_client = live20161101Client(
            open_api_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                # Endpoint 请参考 https://api.aliyun.com/product/live
                endpoint = "live.aliyuncs.com"
            )
        )
        self._cas_client = cas20200407Client(
            open_api_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                # Endpoint 请参考 https://api.aliyun.com/product/cas
                endpoint = "cas.aliyuncs.com"
            )
        )
    
    def iter_certs(self) -> Generator[cas_20200407_models.ListUserCertificateOrderResponseBodyCertificateOrderList, None, None]:
        certs = self._cas_client.list_user_certificate_order(
            cas_20200407_models.ListUserCertificateOrderRequest(
                order_type="UPLOAD",
                show_size=100
            )
        ).body.certificate_order_list
        for c in certs:
            yield c

    def get_cert_by_id(self, cert_id: int) -> cas_20200407_models.GetUserCertificateDetailResponseBody:
        return self._cas_client.get_user_certificate_detail(
            cas_20200407_models.GetUserCertificateDetailRequest(
                cert_id=cert_id
            )
        ).body

    def upload_cert(self, domain_name: str, full_chain: str, private_key: str) -> cas_20200407_models.GetUserCertificateDetailResponseBody:
        cert_name = domain_name.replace(".", "_") + datetime.now().strftime("_%Y%m%dT%H%M%S")
        cert_id = self._cas_client.upload_user_certificate(
            cas_20200407_models.UploadUserCertificateRequest(
                name=cert_name,
                cert=full_chain,
                key=private_key,
            )
        ).body.cert_id
        return self.get_cert_by_id(cert_id)

    def set_cert_for_cdn_domain(self, cert_id: int, domain_name: str) -> Tuple[cas_20200407_models.ListUserCertificateOrderResponseBodyCertificateOrderList, cdn_20180510_models.DescribeUserDomainsResponseBodyDomainsPageData]:
        cert = self.get_cert_by_id(cert_id)
        if not cert:
            return None, None
        for d in self._cdn_client.describe_user_domains(
            cdn_20180510_models.DescribeUserDomainsRequest(
                page_number=1,
                page_size=50,
            ),
        ).body.domains.page_data:
            if d.domain_name == domain_name:
                self._cdn_client.set_cdn_domain_sslcertificate(
                    cdn_20180510_models.SetCdnDomainSSLCertificateRequest(
                        cert_id=cert_id,
                        cert_type="cas",
                        cert_name=cert.name,
                        domain_name=domain_name,
                        sslprotocol="on"
                    )
                )
                return cert, d
        return cert, None

    def set_cert_for_live_domain(self, cert_id: int, domain_name: str) -> Tuple[cas_20200407_models.ListUserCertificateOrderResponseBodyCertificateOrderList, live_20161101_models.DescribeLiveUserDomainsResponseBodyDomainsPageData]:
        cert = self.get_cert_by_id(cert_id)
        if not cert:
            return None, None
        for d in self._live_client.describe_live_user_domains(
            live_20161101_models.DescribeLiveUserDomainsRequest(
                page_number=1,
                page_size=50,
            )
        ).body.domains.page_data:
            if d.domain_name == domain_name:
                self._live_client.set_live_domain_certificate(
                    live_20161101_models.SetLiveDomainCertificateRequest(
                        cert_name=cert.name,
                        cert_type="cas",
                        domain_name=domain_name,
                        sslprotocol="on"
                    )
                )
                return cert, d
        return cert, None
    
    def replace_cert_for_all_matching_cdn_domains(self, new_cert_id: int) -> Tuple[cas_20200407_models.ListUserCertificateOrderResponseBodyCertificateOrderList, List[cdn_20180510_models.DescribeUserDomainsResponseBodyDomainsPageData], Set[int], List[Exception]]:
        new_cert = self.get_cert_by_id(new_cert_id)
        if not new_cert:
            return None, [], []
        old_certs_by_id = {c.certificate_id: c for c in self.iter_certs()}
        replaced_domains = []
        old_cert_ids = set()
        errors = []
        for d, old_certs in self.iter_cdn_domains():
            try:
                to_set = False
                for old_cert in old_certs:
                    if old_cert.cert_id in old_cert_ids:
                        to_set = True
                        break
                    oc = old_certs_by_id.get(int(old_cert.cert_id))
                    if oc and oc.common_name == new_cert.common and oc.certificate_id != new_cert_id:
                        old_cert_ids.add(oc.certificate_id)
                        to_set = True
                        break
                if to_set:
                    self._cdn_client.set_cdn_domain_sslcertificate(
                        cdn_20180510_models.SetCdnDomainSSLCertificateRequest(
                            cert_id=new_cert_id,
                            cert_type="cas",
                            cert_name=new_cert.name,
                            domain_name=d.domain_name,
                            sslprotocol="on"
                        )
                    )
                    replaced_domains.append(d)
                    log.info(f"certificate <{new_cert_id}> set for CDN domain <{d.domain_name}>")
            except Exception as e:
                log.exception(e)
                errors.append(e)
        return new_cert, replaced_domains, old_cert_ids, errors
    
    def replace_cert_for_all_matching_live_domains(self, new_cert_id: int) -> Tuple[cas_20200407_models.ListUserCertificateOrderResponseBodyCertificateOrderList, List[live_20161101_models.DescribeLiveUserDomainsResponseBodyDomainsPageData], Set[int], List[Exception]]:
        new_cert = self.get_cert_by_id(new_cert_id)
        if not new_cert:
            return None, [], []
        old_certs_by_id = {c.certificate_id: c for c in self.iter_certs()}
        old_certs_by_name = {c.name: c for c in old_certs_by_id.values()}
        replaced_domains = []
        old_cert_ids = set()
        errors = []
        for d, old_certs in self.iter_live_domains():
            try:
                to_set = False
                for old_cert in old_certs:
                    oc = old_certs_by_name.get(old_cert.cert_name)
                    if oc and oc.certificate_id in old_cert_ids:
                        to_set = True
                        break
                    if oc and oc.common_name == new_cert.common and oc.certificate_id != new_cert_id:
                        old_cert_ids.add(oc.certificate_id)
                        to_set = True
                        break
                if to_set:
                    self._live_client.set_live_domain_certificate(
                        live_20161101_models.SetLiveDomainCertificateRequest(
                            cert_name=new_cert.name,
                            cert_type="cas",
                            domain_name=d.domain_name,
                            sslprotocol="on"
                        )
                    )
                    replaced_domains.append(d)
                    log.info(f"certificate <{new_cert_id}> set for Live domain <{d.domain_name}>")
            except Exception as e:
                log.exception(e)
                errors.append(e)
        return new_cert, replaced_domains, old_cert_ids, errors

    def delete_cert(self, cert_id: int) -> None:
        self._cas_client.delete_user_certificate(
            cas_20200407_models.DeleteUserCertificateRequest(
                cert_id=cert_id
            )
        )

    def iter_cdn_domains(self) -> Generator[Tuple[cdn_20180510_models.DescribeUserDomainsResponseBodyDomainsPageData, List[cdn_20180510_models.DescribeDomainCertificateInfoResponseBodyCertInfosCertInfo]], None, None]:
        for d in self._cdn_client.describe_user_domains(
            cdn_20180510_models.DescribeUserDomainsRequest(
                page_number=1,
                page_size=50,
            ),
        ).body.domains.page_data:
            if d.ssl_protocol == "off":
                continue
            certs = self._cdn_client.describe_domain_certificate_info(
                cdn_20180510_models.DescribeDomainCertificateInfoRequest(
                    domain_name=d.domain_name
                )        
            ).body.cert_infos.cert_info
            yield d, certs

    def iter_live_domains(self) -> Generator[Tuple[live_20161101_models.DescribeLiveUserDomainsResponseBodyDomainsPageData, List[live_20161101_models.DescribeLiveDomainCertificateInfoResponseBodyCertInfosCertInfo]], None, None]:
        for d in self._live_client.describe_live_user_domains(
            live_20161101_models.DescribeLiveUserDomainsRequest(
                page_number=1,
                page_size=50,
            )
        ).body.domains.page_data:
            certs = self._live_client.describe_live_domain_certificate_info(
                live_20161101_models.DescribeLiveDomainCertificateInfoRequest(
                    domain_name=d.domain_name
                )
            ).body.cert_infos.cert_info
            yield d, certs
