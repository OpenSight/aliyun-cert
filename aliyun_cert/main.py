import os, sys
from pathlib import Path
from typing import List, TextIO
from click.shell_completion import CompletionItem
import rich_click as click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.console import Group
from datetime import datetime, timezone
import logging
from alibabacloud_cdn20180510.client import Client as Cdn20180510Client
from alibabacloud_live20161101.client import Client as live20161101Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_cdn20180510 import models as cdn_20180510_models
from alibabacloud_live20161101 import models as live_20161101_models
import dateutil.parser
from configobj import ConfigObj

from .cert import Aliyun

cprint = Console().print

log = logging.getLogger()
formatter = logging.Formatter("%(asctime)s - %(message)s")
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
log.setLevel(logging.INFO)
log.addHandler(sh)

pass_aliyun = click.make_pass_decorator(Aliyun)


class RenewedDomains(click.ParamType):
    name = "renewed_domains"

    def convert(self, value, param, ctx) -> List[str]:
        if value and isinstance(value, str):
            return value.strip().split(" ")


@click.group()
@click.option("--access-key-id", envvar="ALIYUN_ACCESS_KEY_ID", help="Aliyun access key id")
@click.option("--access-key-secret", envvar="ALIYUN_ACCESS_KEY_SECRET", help="Aliyun access key secret")
@click.option(
    "--access-key-ini-file", 
    envvar="ALIYUN_ACCESS_KEY_INI_FILE", 
    default=str(Path.home()/".secrets/aliyun.ini"), 
    help="Aliyun access key ini file"
)
@click.pass_context
def cli(ctx, access_key_id: str, access_key_secret: str, access_key_ini_file: str) -> None:
    if access_key_id and access_key_secret:
        ctx.obj = Aliyun(access_key_id, access_key_secret)
    elif access_key_ini_file:
        # read ini file
        config = ConfigObj(access_key_ini_file)
        if not config.get("dns_aliyun_key_id") or not config.get("dns_aliyun_key_secret"):
            raise click.UsageError(f"invalid ini file {access_key_ini_file}, please check")
        ctx.obj = Aliyun(
            config.get("dns_aliyun_key_id"),
            config.get("dns_aliyun_key_secret"),
        )
    else:
        raise click.UsageError("access-key-id and access-key-secret or access-key-ini-file is required")


@cli.command()
@click.option("--cdn", is_flag=True, help="show CDN domains")
@click.option("--live", is_flag=True, help="show live domains")
@pass_aliyun
def list_domains(aliyun: Aliyun, cdn: bool, live: bool) -> None:
    """
    show domains and their certificates
    """
    if not cdn and not live:
        raise click.UsageError("please specify --cdn or --live")
    if cdn:
        for d, certs in aliyun.iter_cdn_domains():
            subpanels = []
            for c in certs:
                g = Table.grid()
                g.add_column(min_width=15, justify="left", style="dim")
                g.add_column(justify="left")
                g.add_row("id", c.cert_id)
                g.add_row("domain", c.cert_domain_name)
                g.add_row("type", c.cert_type)
                g.add_row("status", c.status)
                g.add_row("life", c.cert_life)
                if c.cert_expire_time:
                    days_left = calc_left_days(c.cert_expire_time) if c.cert_expire_time else "N/A"
                    g.add_row("expired", "[bold red]TRUE[/]" if days_left < 0 else c.cert_expire_time + f" ({days_left} days left)")
                subpanels.append(
                    Panel(g, title=f"[bold blue]{c.cert_name}[/]", title_align="left")
                )        
            cprint(Panel(Group(*subpanels), title=f"[bold green]{d.domain_name}[/]", title_align="left"))
    if live:
        for d, certs in aliyun.iter_live_domains():
            subpanels = []
            for c in certs:
                g = Table.grid()
                g.add_column(min_width=15, justify="left", style="dim")
                g.add_column(justify="left")
                g.add_row("domain", c.cert_domain_name)
                g.add_row("type", c.cert_type)
                g.add_row("status", c.status)
                g.add_row("life", c.cert_life)
                if c.cert_expire_time:
                    days_left = calc_left_days(c.cert_expire_time) if c.cert_expire_time else "N/A"
                    g.add_row("expired", "[bold red]TRUE[/]" if days_left < 0 else c.cert_expire_time + f" ({days_left} days left)")
                subpanels.append(
                    Panel(g, title=f"[bold blue]{c.cert_name}[/]", title_align="left")
                )        
            cprint(Panel(Group(*subpanels), title=f"[bold green]{d.domain_name}[/]", title_align="left"))
        

@cli.command()
@pass_aliyun
def list_certs(aliyun: Aliyun) -> None:
    """
    show all uploaded certificates in aliyun CAS
    """
    for c in aliyun.iter_certs():
        days_left = "N/A"
        if not c.expired and c.end_date:
            days_left = (dateutil.parser.isoparse(c.end_date) - datetime.now()).days
        g = Table.grid()
        g.add_column(min_width=15, justify="left", style="dim")
        g.add_column(justify="left")
        g.add_row("name", c.name)
        g.add_row("common name", c.common_name)
        g.add_row("SANs", c.sans)
        g.add_row("status", c.status)
        g.add_row("issuer", c.issuer)
        g.add_row("start", c.start_date)
        g.add_row("expired", "[bold red]TRUE[/]" if c.expired else c.end_date + f" ({days_left} days left)")
        cprint(Panel(g, title=f"[bold green]{c.certificate_id}[/]", title_align="left"))


@cli.command()
@click.option("--cert-id", required=True, type=int, help="certificate id")
@pass_aliyun
def get_cert(aliyun: Aliyun, cert_id: int) -> None:
    """
    get certificate detail by id
    """
    c = aliyun.get_cert_by_id(cert_id)
    days_left = "N/A"
    if not c.expired and c.end_date:
        days_left = (dateutil.parser.isoparse(c.end_date) - datetime.now()).days
    g = Table.grid()
    g.add_column(min_width=15, justify="left", style="dim")
    g.add_column(justify="left")
    g.add_row("name", c.name)
    g.add_row("common name", c.common)
    g.add_row("SANs", c.sans)
    g.add_row("issuer", c.issuer)
    g.add_row("start", c.start_date)
    g.add_row("expired", "[bold red]TRUE[/]" if c.expired else c.end_date + f" ({days_left} days left)")
    cprint(Panel(g, title=f"[bold green]{c.id}[/]", title_align="left"))


@cli.command()
@click.argument("full-chain", type=click.File("r"), required=True)
@click.argument("private-key", type=click.File("r"), required=True)
@click.option("--domain", required=True, help="domain name")
@pass_aliyun
def upload_cert(aliyun: Aliyun, full_chain: TextIO, private_key: TextIO, domain: str) -> None:
    """
    upload certificate to aliyun CAS
    """
    cert = aliyun.upload_cert(domain, full_chain.read(), private_key.read())
    cprint(f"cert [bold green]{cert.id}[/] uploaded for {domain}")


@cli.command()
@click.option("--cert-id", required=True, type=int, help="certificate id")
@pass_aliyun
def delete_cert(aliyun: Aliyun, cert_id: int) -> None:
    """
    delete certificate from aliyun CAS
    """
    aliyun.delete_cert(cert_id)
    cprint(f"cert [bold red]{cert_id}[/] deleted")


@cli.command()
@click.option("--cert-id", required=True, type=int, help="certificate id")
@click.option("--domain", required=True, type=str, help="domain name")
@click.option('--service', type=click.Choice(['cdn', 'live'], case_sensitive=False), help="aliyun service type")
@pass_aliyun
def set_cert(aliyun: Aliyun, cert_id: int, domain: str, service: str) -> None:
    """
    set certificate for aliyun domain
    """
    if service == "cdn":
        c, cdn = aliyun.set_cert_for_cdn_domain(cert_id, domain)
        if not c:
            raise click.ClickException(f"certificate {cert_id} not found")
        if not cdn:
            raise click.ClickException(f"CDN domain {domain} not found")
        cprint(f"cert [bold green]{cert_id}[/] set for CDN domain [bold green]{cdn.domain_name}[/]")
    elif service == "live":
        c, live = aliyun.set_cert_for_live_domain(cert_id, domain)
        if not c:
            raise click.ClickException(f"certificate {cert_id} not found")
        if not live:
            raise click.ClickException(f"live domain {domain} not found")
        cprint(f"cert [bold green]{cert_id}[/] set for live domain [bold green]{live.domain_name}[/]")
    else:
        raise click.UsageError("please specify --service cdn or --service live")


@cli.command()
@click.option("--cert-id", required=True, type=int, help="certificate id")
@click.option("--cdn", is_flag=True, help="replace certificates of CDN domains")
@click.option("--live", is_flag=True, help="replace certificates of live domains")
@pass_aliyun
def replace_cert(aliyun: Aliyun, cert_id: int, cdn: bool, live: bool) -> None:
    """
    replace certificate for all domains which using certificate of the same common name
    """
    if not cdn and not live:
        raise click.UsageError("please specify --cdn or --live")
    if cdn:
        aliyun.replace_cert_for_all_matching_cdn_domains(cert_id)
    if live:
        aliyun.replace_cert_for_all_matching_live_domains(cert_id)


@cli.command()
@click.option("--cert-path", envvar="RENEWED_LINEAGE", required=True, help="path to directory containing fullchain.pem and privkey.pem")
@click.option("--renewed_domains", envvar="RENEWED_DOMAINS", type=RenewedDomains(), required=True, help="renewed domain names split by space")
@click.option("--cdn", is_flag=True, help="replace certificates of CDN domains")
@click.option("--live", is_flag=True, help="replace certificates of live domains")
@click.option("--delete-old-cert", is_flag=True, help="delete old certificate after deployment")
@pass_aliyun
def certbot_deploy_hook(aliyun: Aliyun, cert_path, renewed_domains: List[str], cdn: bool, live: bool, delete_old_cert: bool) -> None:
    """
    deploy hook for certbot

    please check "--deploy-hook DEPLOY_HOOK" in
    https://eff-certbot.readthedocs.io/en/stable/using.html

    """
    if not cdn and not live:
        raise click.UsageError("please specify --cdn or --live")
    with open(os.path.join(cert_path, "fullchain.pem"), "r") as f:
        full_chain = f.read()
    with open(os.path.join(cert_path, "privkey.pem"), "r") as f:
        private_key = f.read()
    cert = aliyun.upload_cert(renewed_domains[0], full_chain, private_key)
    log.info(f"certificate for <{' '.join(d for d in renewed_domains)}> uploaded, id: <{cert.id}>")
    cert_id_to_delete = set()
    has_error = False
    if cdn:
        _, _, old_cert_ids, errors = aliyun.replace_cert_for_all_matching_cdn_domains(cert.id)
        cert_id_to_delete.update(old_cert_ids)
        if errors:
            has_error = True
    if live:
        _, _, old_cert_ids, errors = aliyun.replace_cert_for_all_matching_live_domains(cert.id)
        cert_id_to_delete.update(old_cert_ids)
        if errors:
            has_error = True
    if not has_error and delete_old_cert:
        for cert_id in cert_id_to_delete:
            aliyun.delete_cert(cert_id)
            log.info(f"deleted old certificate <{cert_id}>")


def calc_left_days(dts: str) -> int:
    if not dts:
        return -1
    dt = dateutil.parser.isoparse(dts)
    return (dt - datetime.now(tz=timezone.utc)).days
        

if __name__ == "__main__":
    cli()
