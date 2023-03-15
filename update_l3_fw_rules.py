import sys
import os
import argparse
import logging
import logging.config

import meraki
import inquirer
import prettytable

logging.config.fileConfig("logger.conf")
logger = logging.getLogger(__name__)


def getUserChoice(name: str, choices_list: list, message: str) -> str:
    """Generates a list of options that can be selected using up/down arrows
        and returns a dict with selection.

    Args:
        name (str): Name of field being chosen (e.g. "ip_pool", "cdp_neigh")
        choices_list (list): List of choices available to the user
        message (str): Message propmt for the user

    Returns:
        str: Contains the user's choice
    """
    # ANSI formatting vars
    f_head = "\033[95m"
    f_color_green = "\033[92m"
    f_bold = "\033[1m"
    f_end = "\033[0m"
    print(
        f_head
        + f_bold
        + f_color_green
        + 'NOTE: Use arrows to move and "Enter" to confirm.'
        + f_end
    )
    query = [
        inquirer.List(name=name, message=message, choices=choices_list, carousel=True)
    ]
    answer = inquirer.prompt(query)
    return answer[name]


def main():
    # Retrieve all orgs to find match and org_id
    orgs = meraki_api.organizations.getOrganizations()

    org_id = [org["id"] for org in orgs if org["name"] == args.org]

    # Stops issues occuring with no/multiple orgs
    if not org_id or len(org_id) > 1:
        logger.error(
            f"1 organization match not found for: {args.org}. Found: {org_id}. Exiting..."
        )
        sys.exit(1)

    org_id = org_id[0]

    all_org_templates = meraki_api.organizations.getOrganizationConfigTemplates(org_id)

    if not all_org_templates:
        logger.error(f"No Templates within Org: {args.org}. Exiting...")
        sys.exit(1)

    template_choice_id = [
        template["id"]
        for template in all_org_templates
        if template["name"] == args.template
    ]

    if not template_choice_id:
        logger.error(
            f"Compliant Template: {args.template} found in Org: {args.org}. Exiting..."
        )
        sys.exit(1)

    template_to_configure = args.templates_to_configure.split(",")
    template_to_configure = [template.strip() for template in template_to_configure]

    for template in template_to_configure:
        template = template.strip()
        if template not in [template["name"] for template in all_org_templates]:
            logger.error(
                f"Destination Template: {template} not found in Org: {args.org}. Exiting..."
            )
            sys.exit(1)

    logger.info(f"Templates: {args.templates_to_configure} found in Org: {args.org}")

    template_choice_id = template_choice_id[0]

    templates_to_compare = [
        template
        for template in all_org_templates
        if template["name"] in template_to_configure
    ]

    main_fw_rules = meraki_api.appliance.getNetworkApplianceFirewallL3FirewallRules(
        networkId=template_choice_id
    )

    for template in templates_to_compare:
        template["updated"] = False
        template[
            "rules"
        ] = meraki_api.appliance.getNetworkApplianceFirewallL3FirewallRules(
            networkId=template["id"]
        )
        template["rules_in_compliance"] = False
        if template["rules"] == main_fw_rules:
            template["rules_in_compliance"] = True

    table = prettytable.PrettyTable()
    table.title = f"Compliant Template: {args.template}"
    table.field_names = ["Template Name", "Compliant?"]
    for template in templates_to_compare:
        table.add_row([template["name"], template["rules_in_compliance"]])

    if (
        not len(
            [
                template
                for template in templates_to_compare
                if not template.get("rules_in_compliance")
            ]
        )
        > 0
    ):
        logger.info("All Templates in Compliance!")
        sys.exit(0)

    print(table)

    if args.v:
        update_templates = getUserChoice(
            name="Yes/No",
            choices_list=["Yes", "No"],
            message=f"Update templates to match template: {args.template}?",
        )

        if update_templates.lower() != "yes":
            logger.info("User selected 'No' to update. Exiting...")
            sys.exit(0)

    # Removes default rule for updating.
    del main_fw_rules["rules"][-1]

    for template in templates_to_compare:
        if template["rules_in_compliance"]:
            continue
        try:
            meraki_api.appliance.updateNetworkApplianceFirewallL3FirewallRules(
                networkId=template["id"], rules=main_fw_rules["rules"]
            )
            logger.info(f"Template: {template['name']} updated Succesfully!.")
            template["updated"] = True
        except meraki.APIError:
            logger.error(f"** ERROR ** - Template: {template['name']} not Updated!")
            continue

    updated_table = prettytable.PrettyTable()
    updated_table.title = f"Compliant Template: {args.template}"
    updated_table.field_names = ["Template Name", "Compliant?"]
    for template in templates_to_compare:
        updated_table.add_row([template["name"], template["updated"]])

    print(updated_table)

    templates_not_updated = [
        template for template in templates_to_compare if not template["updated"]
    ]

    if templates_not_updated:
        logger.error(f"Templates: {templates_not_updated} not updated...")
        sys.exit(1)


if __name__ == "__main__":
    api_key = os.environ.get("MERAKI_API_KEY")

    if not api_key:
        raise TypeError(
            "MERAKI_API_KEY not defined as Env variable..."
            "\nPlease set and re-run program."
        )

    meraki_api = meraki.DashboardAPI(api_key=api_key, suppress_logging=True)

    parser = argparse.ArgumentParser(
        description="Updates Meraki Templates FW rules from specified template."
    )

    parser.add_argument("org", help="Meraki Organization name")
    parser.add_argument("template", help="Compliant template name")
    parser.add_argument(
        "templates_to_configure",
        help="Comma separated string of template names to make compliant",
    )

    parser.add_argument(
        "-v",
        help="Ask User for verification before updating FW rules. Defaults to False",
        action="store_true",
    )

    args = parser.parse_args()

    main()
