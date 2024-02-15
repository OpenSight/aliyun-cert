"""DNS Authenticator for Aliyun DNS."""
import os
import logging
from typing import Callable, Optional
from alibabacloud_alidns20150109.client import Client as Alidns20150109Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_alidns20150109 import models as alidns_20150109_models

from certbot.plugins import dns_common
from certbot import errors

logger = logging.getLogger(__name__)

class Authenticator(dns_common.DNSAuthenticator):
    """DNS Authenticator for Aliyun DNS

    This Authenticator uses the Aliyun DNS API to fulfill a dns-01 challenge.
    """

    description = 'Obtain certificates using a DNS TXT record (if you are using Aliyun DNS).'
    ttl = 600
    _alidns_client = None

    def __init__(self, *args, **kwargs):
        super(Authenticator, self).__init__(*args, **kwargs)
        self.credentials: Optional[dns_common.CredentialsConfiguration] = None

    @classmethod
    def add_parser_arguments(cls, add: Callable[..., None], default_propagation_seconds: int = 10) -> None:  # pylint: disable=arguments-differ
        super().add_parser_arguments(add, default_propagation_seconds)
        add('credentials', help='Aliyun credentials INI file.')

    def more_info(self):  # pylint: disable=missing-docstring,no-self-use
        return 'This plugin configures a DNS TXT record to respond to a dns-01 challenge using ' + \
               'the Aliyun DNS API.'

    def _validate_credentials(self, credentials: dns_common.CredentialsConfiguration) -> None:
        key_id = credentials.conf('key-id')
        key_secret = credentials.conf('key-secret')
        if not key_id or not key_secret:
            raise errors.PluginError(
                '{}: dns_aliyun_key_id and dns_aliyun_key_secret are required.'
                .format(credentials.confobj.filename)
            )

    def _setup_credentials(self) -> None:
        self.credentials = self._configure_credentials(
            'credentials',
            'Aliyun credentials INI file',
            None,
            self._validate_credentials
        )

    def _perform(self, domain, validation_name, validation):
        domain = self._find_domain_name(domain)
        rr = validation_name[:validation_name.rindex('.' + domain)]
        self._get_alidns_client().add_domain_record(
            alidns_20150109_models.AddDomainRecordRequest(
                domain_name=domain,
                rr=rr,
                type="TXT",
                value=validation,
                ttl=self.ttl,
            )
        )

    def _cleanup(self, domain, validation_name, validation):
        domain = self._find_domain_name(domain)
        rr = validation_name[:validation_name.rindex('.' + domain)]
        record_id = self._find_domain_record_id(domain, rr=rr, typ='TXT')
        self._get_alidns_client().delete_domain_record(
            alidns_20150109_models.DeleteDomainRecordRequest(
                record_id=record_id
            )
        )

    def _get_alidns_client(self):
        if not self._alidns_client:
            if not self.credentials:
                raise Exception('No credentials')
            key_id = self.credentials.conf('key-id')
            key_secret = self.credentials.conf('key-secret')
            if not key_id or not key_secret:
                raise Exception('No key-id or key-secret')
            self._alidns_client = Alidns20150109Client(
                open_api_models.Config(
                    access_key_id=key_id,
                    access_key_secret=key_secret,
                    # Endpoint 请参考 https://api.aliyun.com/product/Alidns
                    endpoint="alidns.cn-hangzhou.aliyuncs.com"
                )
            )
        return self._alidns_client

    def _find_domain_name(self, domain):
        domain_name_guesses = dns_common.base_domain_name_guesses(domain)
        for domain_name in domain_name_guesses:
            response = self._get_alidns_client().describe_domains(
                alidns_20150109_models.DescribeDomainsRequest(
                    key_word=domain_name
                )
            )
            for d in response.body.domains.domain:
                if d.domain_name == domain_name:
                    return domain_name
        raise errors.PluginError('Unable to determine zone identifier for {0} using zone names: {1}'
                                 .format(domain, domain_name_guesses))
    
    def _find_domain_record_id(self, domain, rr = '', typ = '', value = '') -> str:
        for r in self._get_alidns_client().describe_domain_records(
            alidns_20150109_models.DescribeDomainRecordsRequest(
                domain_name=domain,
                rrkey_word=rr,
                type_key_word=typ,
                value_key_word=value
            )
        ).body.domain_records.record:
            if r.rr == rr and isinstance(r.record_id, str):
                return r.record_id
        raise errors.PluginError('Unexpected error determining record identifier for {0}: {1}'
                                 .format(rr, 'record not found'))
