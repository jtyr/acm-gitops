#!/usr/bin/env python

import argparse
import logging
import os
import sys
import yaml

from jinja2 import Environment, FileSystemLoader


# This helps to improve YAML formatting
class MyDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(MyDumper, self).increase_indent(flow, False)


# Custom argparse action that allows to read default value from env var
class EnvDefault(argparse.Action):
    def __init__(self, envvar, required=False, default=None, **kwargs):
        # Overwrite defaut value with env var value
        if envvar in os.environ:
            default = os.environ[envvar]

        # Prevent failure if we found default value in env var
        if required and default:
            required = False

        super(EnvDefault, self).__init__(
            default=default,
            required=required,
            **kwargs,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)


# Tools used in other classes
class Tools:
    def __init__(self, log):
        self.log = log

    # Read and parse YAML file
    def read_yaml_file(self, filename):
        self.log.debug("Reading YAML inventory '%s'" % filename)

        try:
            with open(filename, "r") as stream:
                try:
                    data = yaml.safe_load(stream)
                except yaml.YAMLError as e:
                    raise Exception("cannot parse YAML file '%s': %s" % (filename, e))
        except IOError as e:
            raise Exception("cannot open file '%s': %s" % (filename, e))

        return data

    # Write YAML data into a file
    def write_yaml_file(self, data, filename=None, stdout=False):
        data = yaml.dump(data, Dumper=MyDumper, default_flow_style=False)

        self.write_file(data, filename=filename, stdout=stdout)

    # Write data into a file
    def write_file(self, data, target_file=None, stdout=False):
        if stdout:
            self.log.debug("Printing into STDOUT")

            output = sys.stdout
        else:
            self.log.debug("Printing into file '%s'" % target_file)

            # Check if the directory exist
            target_dir = os.path.dirname(target_file)

            if not os.path.exists(target_dir):
                self.log.debug("Creating directory '%s'" % target_dir)

                try:
                    os.makedirs(target_dir, mode=0o755)
                except Exception as e:
                    raise Exception(
                        "cannot create directory '%s': %s" % (target_dir, e)
                    )

            try:
                output = open(target_file, "w")
            except IOError as e:
                raise Exception(
                    "cannot open file '%s' for write: %s" % (target_file, e)
                )

        output.write(data)

        if not stdout:
            try:
                output.close()
            except IOError as e:
                raise Exception("cannot close file '%s': %s" % (target_file, e))


class Common:
    def __init__(self, app, meta_path, logger, env=None):
        # Class params
        self.app = app
        self.env = env
        self.meta_path = meta_path
        self.log = logger

        # Make tools accessible
        self.tools = Tools(self.log)

    # Reads promotions.yaml file for particular application
    def _get_promotion(self):
        self.log.debug("Reading promotion file")

        try:
            promotion = self.tools.read_yaml_file(
                os.path.join(self.meta_path, self.app, "promotion.yaml"),
            )
        except Exception as e:
            raise Exception("cannot read file 'promotion.yaml': %s" % e)

        if "promotion" not in promotion:
            raise Exception(
                "there is no promotion defined in the file 'promotion.yaml'"
            )

        return promotion["promotion"]


class Generate(Common):
    def __init__(
        self,
        app,
        env,
        zone,
        meta_path,
        release_path,
        template_path,
        subscription_template,
        application_template,
        logger,
    ):
        # Call parent class
        super().__init__(app=app, env=env, meta_path=meta_path, logger=logger)

        # Class params
        self.zone = zone
        self.meta_path = meta_path
        self.release_path = release_path
        self.template_path = template_path
        self.subscription_template = subscription_template
        self.application_template = application_template

        # Data cplaceholders (cache)
        self._params = None
        self._values = None

        # Prepare templating
        self.j2e = Environment(
            loader=FileSystemLoader(template_path.split(",")),
            keep_trailing_newline=True,
        )
        self.j2e.filters["merge"] = self._jinja2_filter_merge
        self.j2e.filters["to_yaml"] = self._jinja2_filter_to_yaml

    # Reads parameters.yaml file for particular application
    def _get_params(self):
        # Use cache
        if self._params is not None:
            return self._params

        self.log.debug("Reading parameters file")

        try:
            self._params = self.tools.read_yaml_file(
                os.path.join(self.meta_path, self.app, "parameters.yaml"),
            )
        except Exception as e:
            raise Exception("cannot read file 'parameters.yaml': %s" % e)

        # Set default values
        if "chart" in self._params and (
            "values" not in self._params["chart"]
            or not isinstance(self._params["chart"]["values"], dict)
        ):
            self._params["chart"]["values"] = {}

        # Set default labels
        if "labels" not in self._params or not isinstance(self._params["labels"], dict):
            self._params["labels"] = {}

        # Convert all labels to string
        for k, v in self._params["labels"].items():
            if not isinstance(v, str):
                self._params[k] = str(v)

        return self._params

    # Reads values file for particular application, environment and zone
    def _get_values(self):
        val_file = "%s-%s.yaml" % (self.env, self.zone)
        val_file_full = os.path.join(
            self.meta_path,
            self.app,
            "values",
            val_file,
        )

        # Values file is optional
        if not os.path.exists(val_file_full):
            self.log.debug("No zone-specific values are set in '%s'" % val_file_full)

            self._values = {
                "deepMerge": False,
                "values": {},
            }

        # Use cache
        if self._values is not None:
            return self._values

        self.log.debug("Reading values file '%s'" % val_file)

        try:
            self._values = self.tools.read_yaml_file(val_file_full)
        except Exception as e:
            raise Exception("cannot read values file '%s': %s" % (val_file, e))

        # Set default values
        if "values" not in self._values or not isinstance(self._values["values"], dict):
            self._values["values"] = {}

        # Set default deepMerge value
        if "deepMerge" not in self._values or not isinstance(
            self._values["deepMerge"], bool
        ):
            self._values["deepMerge"] = False

        return self._values

    # Custom Jinja2 filter that allows to merge two dicts
    def _jinja2_filter_merge(self, dict1, dict2, deep=False):
        if not deep:
            dict1.update(dict2)

            return dict1

        if not isinstance(dict1, dict) or not isinstance(dict2, dict):
            return dict2

        for k in dict2:
            if k in dict1:
                dict1[k] = self._jinja2_filter_merge(dict1[k], dict2[k], deep=deep)
            else:
                dict1[k] = dict2[k]

        return dict1

    # Custom Jinja2 filter that allows to produce YAML string
    def _jinja2_filter_to_yaml(self, data):
        return yaml.dump(data, Dumper=MyDumper, default_flow_style=False).rstrip()

    # Generate Application resource
    def application(self):
        self.log.info("Generating Application")

        params = self._get_params()

        # Allow to override template via params
        if "template" in params and "application" in params["template"]:
            app_template = params["template"]["application"]
        else:
            app_template = self.application_template

        try:
            template = self.j2e.get_template(app_template)

            app = template.render(
                app=self.app,
                env=self.env,
                params=params,
                values=self._get_values(),
            )
        except Exception as e:
            raise Exception("templating error: %s" % e)

        target_file = os.path.join(
            self.release_path,
            self.env,
            "applications",
            "%s.yaml" % self.app,
        )

        try:
            self.tools.write_file(app, target_file=target_file)
        except Exception as e:
            raise Exception(
                "failed to write Subscription into file '%s': %s" % (target_file, e)
            )

    # Generate Subscription resource
    def subscription(self):
        self.log.info("Generating Subscription")

        params = self._get_params()

        # Allow to override template via params
        if "template" in params and "subscription" in params["template"]:
            sub_template = params["template"]["subscription"]
        else:
            sub_template = self.subscription_template

        try:
            template = self.j2e.get_template(sub_template)

            sub = template.render(
                app=self.app,
                env=self.env,
                zone=self.zone,
                params=params,
                values=self._get_values(),
            )
        except Exception as e:
            raise Exception("templating error: %s" % e)

        target_file = os.path.join(
            self.release_path,
            self.env,
            "subscriptions",
            "%s-%s.yaml" % (self.app, self.zone),
        )

        try:
            self.tools.write_file(sub, target_file=target_file)
        except Exception as e:
            raise Exception(
                "failed to write Subscription into file '%s': %s" % (target_file, e)
            )


class Get(Common):
    def __init__(self, app, meta_path, logger, env=None):
        # Call parent class
        super().__init__(app=app, env=env, meta_path=meta_path, logger=logger)

    # Get list of zones for the particular environment
    def zones(self):
        self.log.info("Getting Zones list")

        promotion = self._get_promotion()
        data = {}
        found = False

        # Extract zones and sort them by priorities
        for p in promotion:
            if "env" in p and p["env"] == self.env and "placements" in p:
                for info in p["placements"]:
                    priority = 0

                    if "priority" in info:
                        priority = info["priority"]

                    if priority not in data:
                        data[priority] = []

                    data[priority].append(info["name"])

                    if not found:
                        found = True

            if found:
                break
        else:
            raise Exception(
                "environment '%s' not present in the 'promotion.yaml' file" % self.env
            )

        for zones in data.values():
            print(",".join(zones))

    # Get the name of the first environment
    def first_env(self):
        self.log.info("Getting first env")

        promotion = self._get_promotion()

        if len(promotion) == 0:
            raise Exception("no environment present in the 'promotion.yaml' file")

        if "env" not in promotion[0]:
            raise Exception("missing environment name in the first promotion item")

        print(promotion[0]["env"])

    # Get the name of the next environment
    def next_env(self):
        self.log.info("Getting next env")

        promotion = self._get_promotion()
        found = False

        for p in promotion:
            if found:
                print(p["env"])

                break

            if "env" in p and p["env"] == self.env:
                found = True
        else:
            if found:
                self.log.info(
                    "Environment '%s' was the last one for promotion" % self.env
                )
            else:
                raise Exception(
                    "environment '%s' not present in the 'promotion.yaml' file"
                    % self.env
                )

    # Get the name of the previous environment
    def prev_env(self):
        self.log.info("Getting prev env")

        promotion = self._get_promotion()
        prev = ""

        for p in promotion:
            if "env" in p and p["env"] == self.env:
                if prev != "":
                    print(prev)

                break

            prev = p["env"]
        else:
            raise Exception(
                "environment '%s' does not exist in the 'promotion.yaml' file"
                % self.env
            )

        if prev == "":
            self.log.warning(
                "Environment '%s' is the first environment in the promotion" % self.env
            )


class Validate(Common):
    def __init__(self, app, meta_path, release_path, logger):
        # Call parent class
        super().__init__(app=app, meta_path=meta_path, logger=logger)

        # Class params
        self.release_path = release_path

    # Verify that there is a placement file for each promotion placement
    def placements(self):
        promotion = self._get_promotion()

        for p in promotion:
            if "env" in p and "placements" in p:
                for info in p["placements"]:
                    if "name" not in info:
                        self.log.warn("Missing placement name for '%s' env" % p["env"])

                        continue

                    filename = os.path.join(
                        p["env"], "placement-rules", "%s.yaml" % info["name"]
                    )
                    filename_full = os.path.join(self.release_path, filename)

                    # Verify that the file exists
                    if os.path.exists(filename_full):
                        self.log.info("Found '%s'" % filename)
                    else:
                        raise Exception("cannot find placement file '%s'" % filename)

                    try:
                        p_data = self.tools.read_yaml_file(filename_full)
                    except Exception as e:
                        raise Exception("cannot read file '%s': %s" % (filename, e))

                    # Verify that the YAML file contains expected CR name
                    if (
                        "metadata" in p_data
                        and "name" in p_data["metadata"]
                        and p_data["metadata"]["name"]
                        == "%s-%s" % (p["env"], info["name"])
                    ):
                        self.log.info("Found 'name: %s-%s'" % (p["env"], info["name"]))
                    else:
                        raise Exception(
                            "cannot find 'name: %s-%s'" % (p["env"], info["name"])
                        )


def parse_args():
    parser = argparse.ArgumentParser(description="Generate and validate ACM resources.")

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Show debug messages.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show verbose messages.",
    )
    parser.add_argument(
        "-m",
        "--meta-path",
        metavar="PATH",
        default=".",
        action=EnvDefault,
        envvar="ACM_META_PATH",
        help="Path to the ACM meta directory (env: ACM_META_PATH). (default: .)",
    )

    subparsers = parser.add_subparsers(help="Actions.")

    parser_generate = subparsers.add_parser(
        "generate",
        help="Generate ACM resources.",
    )
    parser_generate.set_defaults(action="generate")
    parser_generate.add_argument(
        "app",
        help="Name of the application.",
    )
    parser_generate.add_argument(
        "env",
        help="Environment name.",
    )
    parser_generate.add_argument(
        "zone",
        help="Zone name.",
    )
    parser_generate.add_argument(
        "-r",
        "--release-path",
        metavar="PATH",
        required=True,
        action=EnvDefault,
        envvar="ACM_RELEASE_PATH",
        help="Path to the release directory (env: ACM_RELEASE_PATH).",
    )
    parser_generate.add_argument(
        "-t",
        "--template-path",
        metavar="PATH",
        default=os.path.dirname(__file__),
        action=EnvDefault,
        envvar="ACM_TEMPLATE_PATH",
        help=(
            "Comma-separated list of directories where search for templates "
            "(env: ACM_TEMPLATE_PATH). (default: %s)" % os.path.dirname(__file__)
        ),
    )
    parser_generate.add_argument(
        "-s",
        "--subscription-template",
        metavar="NAME",
        default="subscription.yaml.j2",
        action=EnvDefault,
        envvar="ACM_SUBSCRIPTION_TEMPLATE",
        help=(
            "Name of the ACM Subscription template "
            "(env: ACM_SUBSCRIPTION_TEMPLATE). (default: subscription.yaml.j2)"
        ),
    )
    parser_generate.add_argument(
        "-a",
        "--application-template",
        metavar="NAME",
        default="application.yaml.j2",
        action=EnvDefault,
        envvar="ACM_APPLICATION_TEMPLATE",
        help=(
            "Name of the ACM Application template "
            "(env: ACM_APPLICATION_TEMPLATE). (default: application.yaml.j2)"
        ),
    )

    parser_validate = subparsers.add_parser(
        "validate",
        help="Validate metadata.",
    )
    parser_validate.set_defaults(action="validate")
    parser_validate.add_argument(
        "-r",
        "--release-path",
        metavar="PATH",
        required=True,
        action=EnvDefault,
        envvar="ACM_RELEASE_PATH",
        help="Path to the release directory (env: ACM_RELEASE_PATH).",
    )
    validate_subparsers = parser_validate.add_subparsers(help="Actions.")

    parser_validate_placements = validate_subparsers.add_parser(
        "placements",
        help="Validate placements of the application.",
    )
    parser_validate_placements.set_defaults(action="validate_placements")
    parser_validate_placements.add_argument(
        "app",
        help="Name of the application.",
    )

    parser_get = subparsers.add_parser(
        "get",
        help="Get information.",
    )
    parser_get.set_defaults(action="get")
    get_subparsers = parser_get.add_subparsers(help="Actions.")

    parser_get_zones = get_subparsers.add_parser(
        "zones",
        help="Get zones list for the environment.",
    )
    parser_get_zones.set_defaults(action="get_zones")
    parser_get_zones.add_argument(
        "app",
        help="Name of the application.",
    )
    parser_get_zones.add_argument(
        "env",
        help="Environment name.",
    )

    parser_get_first_env = get_subparsers.add_parser(
        "first-env",
        help="Get name of the first environment.",
    )
    parser_get_first_env.set_defaults(action="get_first_env")
    parser_get_first_env.add_argument(
        "app",
        help="Name of the application.",
    )

    parser_get_next_env = get_subparsers.add_parser(
        "next-env",
        help="Get name of the next environment.",
    )
    parser_get_next_env.set_defaults(action="get_next_env")
    parser_get_next_env.add_argument(
        "app",
        help="Name of the application.",
    )
    parser_get_next_env.add_argument(
        "env",
        help="Environment name.",
    )

    parser_get_prev_env = get_subparsers.add_parser(
        "prev-env",
        help="Get name of the previous environment.",
    )
    parser_get_prev_env.set_defaults(action="get_prev_env")
    parser_get_prev_env.add_argument(
        "app",
        help="Name of the application.",
    )
    parser_get_prev_env.add_argument(
        "env",
        help="Environment name.",
    )

    return parser, parser.parse_args()


def main():
    # Read command line arguments
    parser, args = parse_args()

    # Setup logger
    format = "%(levelname)s: %(message)s"
    log_level = logging.ERROR

    if args.debug:
        log_level = logging.DEBUG
    elif args.verbose:
        log_level = logging.INFO

    logging.basicConfig(level=log_level, format=format)

    log = logging.getLogger(__name__)

    # Check input parameters
    if "action" not in args:
        log.error("No action specified!")
        parser.print_help()
        sys.exit(1)

    # Decide what to do
    if args.action == "generate":
        gen = Generate(
            app=args.app,
            env=args.env,
            zone=args.zone,
            meta_path=args.meta_path,
            release_path=args.release_path,
            template_path=args.template_path,
            subscription_template=args.subscription_template,
            application_template=args.application_template,
            logger=log,
        )

        try:
            gen.application()
        except Exception as e:
            log.error("Failed to generate Application: %s" % e)
            sys.exit(1)

        try:
            gen.subscription()
        except Exception as e:
            log.error("Failed to generate Subscription: %s" % e)
            sys.exit(1)
    elif args.action.startswith("get_zones"):
        get = Get(
            app=args.app,
            env=args.env,
            meta_path=args.meta_path,
            logger=log,
        )

        try:
            get.zones()
        except Exception as e:
            log.error("Failed to get zones list: %s" % e)
            sys.exit(1)
    elif args.action == "get_first_env":
        get = Get(
            app=args.app,
            meta_path=args.meta_path,
            logger=log,
        )

        try:
            get.first_env()
        except Exception as e:
            log.error("Failed to get name of the first environment: %s" % e)
            sys.exit(1)
    elif args.action == "get_next_env":
        get = Get(
            app=args.app,
            env=args.env,
            meta_path=args.meta_path,
            logger=log,
        )

        try:
            get.next_env()
        except Exception as e:
            log.error("Failed to get name of the next environment: %s" % e)
            sys.exit(1)
    elif args.action == "get_prev_env":
        get = Get(
            app=args.app,
            env=args.env,
            meta_path=args.meta_path,
            logger=log,
        )

        try:
            get.prev_env()
        except Exception as e:
            log.error("Failed to get name of the prev environment: %s" % e)
            sys.exit(1)
    elif args.action == "validate_placements":
        val = Validate(
            app=args.app,
            meta_path=args.meta_path,
            release_path=args.release_path,
            logger=log,
        )

        try:
            val.placements()
        except Exception as e:
            log.error("Failed to run placements validation: %s" % e)
            sys.exit(1)
    else:
        log.error("No '%s' action specified!" % args.action)

        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for choice, subparser in action.choices.items():
                    if choice == args.action:
                        subparser.print_help()

        sys.exit(1)


if __name__ == "__main__":
    main()
