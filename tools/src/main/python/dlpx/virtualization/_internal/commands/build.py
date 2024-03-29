#
# Copyright (c) 2019 by Delphix. All rights reserved.
#

import base64
import compileall
import copy
import json
import logging
import os
import StringIO
import zipfile

from dlpx.virtualization._internal import (
    codegen,
    exceptions,
    file_util,
    package_util,
    plugin_util,
    util_classes,
)

logger = logging.getLogger(__name__)

TYPE = "Plugin"
LOCALE_DEFAULT = "en-us"
VIRTUAL_SOURCE_TYPE = "PluginVirtualSourceDefinition"
DISCOVERY_DEFINITION_TYPE = "PluginDiscoveryDefinition"
STAGED_LINKED_SOURCE_TYPE = "PluginLinkedStagedSourceDefinition"
DIRECT_LINKED_SOURCE_TYPE = "PluginLinkedDirectSourceDefinition"


def build(plugin_config, upload_artifact, generate_only, skip_id_validation):
    """This builds the plugin using the configurations provided in config yaml
    file provided as input. It reads schemas and source code from the files
    given in yaml file, generates an encoded string of zip of source code,
    prepares plugin json output file that can be used by upload command later.

    Args:
        plugin_config: Plugin config file used for building plugin.
        upload_artifact: The file to which output of build  is written to.
        generate_only: Only generate python classes from schema definitions.
        skip_id_validation: Skip validation of the plugin id.
    """
    logger.debug(
        "Build parameters include plugin_config: %s, upload_artifact: %s,"
        " generate_only: %s",
        plugin_config,
        upload_artifact,
        generate_only,
    )

    # Read content of the plugin config  file provided and perform validations
    logger.info("Reading and validating plugin config file %s", plugin_config)
    try:
        result = plugin_util.read_and_validate_plugin_config_file(
            plugin_config, not generate_only, False, skip_id_validation
        )
    except exceptions.UserError as err:
        raise exceptions.BuildFailedError(err)

    plugin_config_content = result.plugin_config_content
    logger.debug("plugin config file content is : %s", result.plugin_config_content)

    schema_file = plugin_util.get_schema_file_path(
        plugin_config, plugin_config_content["schemaFile"]
    )

    # Read schemas from the file provided in the config and validate them
    logger.info("Reading and validating schemas from %s", schema_file)

    try:
        result = plugin_util.read_and_validate_schema_file(
            schema_file, not generate_only
        )
    except exceptions.UserError as err:
        raise exceptions.BuildFailedError(err)

    schemas = result.plugin_schemas
    logger.debug("schemas found: %s", schemas)

    # Resolve the paths for source directory and schema file
    src_dir = file_util.get_src_dir_path(plugin_config, plugin_config_content["srcDir"])
    logger.debug("Source directory path resolved is %s", src_dir)

    #
    # Call directly into codegen to generate the python classes and make sure
    # the ones we zip up are up to date with the schemas.
    #
    try:
        codegen.generate_python(
            plugin_config_content["name"],
            src_dir,
            os.path.dirname(plugin_config),
            schemas,
        )
    except exceptions.UserError as err:
        raise exceptions.BuildFailedError(err)

    if generate_only:
        #
        # If the generate_only flag is set then just return after generation
        # has happened.
        #
        logger.info("Generating python code only. Skipping artifact build.")
        return

    #
    # Validate the plugin config content by importing the module
    # and check the entry point as well. Returns a manifest on
    # successful validation.
    #
    try:
        result = plugin_util.get_plugin_manifest(
            plugin_config, plugin_config_content, not generate_only, skip_id_validation
        )
    except exceptions.UserError as err:
        raise exceptions.BuildFailedError(err)

    plugin_manifest = {}
    if result:
        plugin_manifest = result.plugin_manifest
        if result.warnings:
            warning_msg = util_classes.MessageUtils.warning_msg(result.warnings)
            logger.warn(
                "{}\n{} Warning(s). {} Error(s).".format(
                    warning_msg, len(result.warnings["warning"]), 0
                )
            )

    # Prepare the output artifact.
    try:
        plugin_output = prepare_upload_artifact(
            plugin_config_content, src_dir, schemas, plugin_manifest
        )
    except exceptions.UserError as err:
        raise exceptions.BuildFailedError(err)

    # Write it to upload_artifact as json.
    try:
        generate_upload_artifact(upload_artifact, plugin_output)
    except exceptions.UserError as err:
        raise exceptions.BuildFailedError(err)

    logger.info("Successfully generated artifact file at %s.", upload_artifact)

    logger.warn("\nBUILD SUCCESSFUL.")


def prepare_upload_artifact(plugin_config_content, src_dir, schemas, manifest):
    #
    # This is the output dictionary that will be written
    # to the upload_artifact.
    #
    return {
        # Hard code the type to a set default.
        "type": TYPE,
        #
        # Delphix Engine still accepts only name and prettyName and
        # hence name is mapped to id and prettyName to name.
        # Delphix Engine does not accept upper case letters for name field,
        # so we convert the name to lowercase letters.
        # This will be changed as part of POST GA task PYT-628
        #
        "name": plugin_config_content["id"].lower(),
        "prettyName": plugin_config_content["name"],
        "version": plugin_config_content["version"],
        # set default value of locale to en-us
        "defaultLocale": plugin_config_content.get("defaultLocale", LOCALE_DEFAULT),
        # set default value of language to PYTHON27
        "language": plugin_config_content["language"],
        "hostTypes": plugin_config_content["hostTypes"],
        "entryPoint": plugin_config_content["entryPoint"],
        "buildApi": package_util.get_build_api_version(),
        "engineApi": package_util.get_engine_api_version(),
        "rootSquashEnabled": plugin_config_content.get("rootSquashEnabled", True),
        "sourceCode": zip_and_encode_source_files(src_dir),
        "virtualSourceDefinition": {
            "type": VIRTUAL_SOURCE_TYPE,
            "parameters": schemas["virtualSourceDefinition"],
        },
        "linkedSourceDefinition": {
            "type": get_linked_source_definition_type(plugin_config_content),
            "parameters": schemas["linkedSourceDefinition"],
        },
        "discoveryDefinition": prepare_discovery_definition(
            plugin_config_content, schemas
        ),
        "snapshotSchema": schemas["snapshotDefinition"],
        "manifest": manifest,
    }


def get_linked_source_definition_type(plugin_config_content):
    if "STAGED" == plugin_config_content["pluginType"].upper():
        return STAGED_LINKED_SOURCE_TYPE
    else:
        return DIRECT_LINKED_SOURCE_TYPE


def prepare_discovery_definition(config_content, schemas):
    """
    We need to prepare discoveryDefinition manually since it is split into
    repositoryDefinition and sourceConfigDefinition in the schemas file and
    manualSourceConfigDiscovery is moved to config yml as
    manualDiscovery. repositoryIdentityFields and repositoryNameField are
    renamed to identityFields and nameField respectively for
    repositoryDefinition. sourceConfigIdentityFields and sourceConfigNameField
    are renamed to identityFields and nameField respectively for
    sourceConfigDefinition.

    Also, identityFields and nameField are moved into their
    corresponding definitions, so we will need to remove them using
    pop function before using the corresponding schemas provided in schemaFile
    """

    #
    # Copy repositoryDefinition and sourceConfigDefinition into new dicts for
    # required manipulation
    #
    schema_repo_def = copy.deepcopy(schemas["repositoryDefinition"])
    schema_source_config_def = copy.deepcopy(schemas["sourceConfigDefinition"])

    return {
        "type": DISCOVERY_DEFINITION_TYPE,
        # set manualSourceConfigDiscovery to default value
        "manualSourceConfigDiscovery": config_content.get("manualDiscovery", True),
        # identityFields in schema becomes repositoryIdentityFields
        "repositoryIdentityFields": schema_repo_def.pop("identityFields"),
        "repositoryNameField": schema_repo_def.pop("nameField", None),
        "repositorySchema": schema_repo_def,
        #
        # Transform identityFields and nameField into appropriate fields
        # expected in output artifact.
        #
        "sourceConfigIdentityFields": schema_source_config_def.pop(
            "identityFields", None
        ),
        "sourceConfigNameField": schema_source_config_def.pop("nameField"),
        "sourceConfigSchema": schema_source_config_def,
    }


def generate_upload_artifact(upload_artifact, plugin_output):
    # dump plugin_output JSON into upload_artifact file
    logger.info("Generating upload_artifact file at %s", upload_artifact)
    try:
        with open(upload_artifact, "w") as f:
            json.dump(plugin_output, f, indent=4)
    except IOError as err:
        raise exceptions.UserError(
            "Failed to write upload_artifact file to {}. Error code: {}."
            " Error message: {}".format(
                upload_artifact, err.errno, os.strerror(err.errno)
            )
        )


def zip_and_encode_source_files(source_code_dir):
    """
    Given a path, returns a zip file of all non .py files as a base64 encoded
    string *.py files are skipped to imitate the SDK's build script.
    We skip them because they cannot be imported in the secure context.
    Jython creates a class loader to import .py files which the
    security manager prohibits.
    """

    #
    # The contents of the zip should have relative and not absolute paths or
    # else the imports won't work as expected.
    #
    cwd = os.getcwd()
    try:
        os.chdir(source_code_dir)
        ret_val = compileall.compile_dir(
            source_code_dir, ddir=".", force=True, quiet=True
        )
        if ret_val == 0:
            raise exceptions.UserError(
                "Failed to compile source code in the directory {}.".format(
                    source_code_dir
                )
            )
        out_file = StringIO.StringIO()
        with zipfile.ZipFile(out_file, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for root, _, files in os.walk("."):
                for filename in files:
                    if not filename.endswith(".py"):
                        logger.debug("Adding %s to zip.", os.path.join(root, filename))
                        zip_file.write(os.path.join(root, filename))
        encoded_bytes = base64.b64encode(out_file.getvalue())
        out_file.close()
        return encoded_bytes

    except OSError as os_err:
        raise exceptions.UserError(
            "Failed to read source code directory {}. Error code: {}."
            " Error message: {}".format(
                source_code_dir, os_err.errno, os.strerror(os_err.errno)
            )
        )
    except UnicodeError as uni_err:
        raise exceptions.UserError(
            "Failed to base64 encode source code in the directory {}. "
            "Error message: {}".format(source_code_dir, uni_err.reason)
        )
    finally:
        os.chdir(cwd)
