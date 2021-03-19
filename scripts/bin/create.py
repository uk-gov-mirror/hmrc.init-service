#!/usr/bin/env python

import sys
import argparse
import os
import distutils.core
import subprocess
import fileinput
import shutil
import pyratemp
from urllib import request as url_request
import json
from xml.dom.minidom import parse
import re


def required_environment_directory(environment_variable, description_for_error):
    directory = os.environ.get(environment_variable, None)
    if not directory:
        print("'%s' environment variable is required. You can add this to your ~/.bash_profile by adding the line %s=[%s]" % (
            environment_variable, environment_variable, description_for_error))
        exit(1)
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        print("Error: '%s' environment variable points to non-existent directory: %s" % (
            environment_variable, directory))
        sys.exit(1)
    return directory


workspace = required_environment_directory("WORKSPACE", "your workspace root dir")


def get_latest_sbt_plugin_version_in_open(artifact):
    return get_sbt_plugin_version_info_from_bintray(artifact)


def get_latest_library_version_in_open(artifact, scala_binary_version):
    maven_metadata = get_library_version_info_from_bintray(artifact + "_" + scala_binary_version)

    try:
        data = maven_metadata.getElementsByTagName("versioning")[0]
    except:
        print("Unable to get latest version from bintray")
        return None

    latest = data.getElementsByTagName("latest")[0].firstChild.nodeValue
    if re.search("-play-(\d)*$", latest) and not re.search("-play-28$", latest):
        raise Exception("ERROR: Invalid dependency found '%s'" % latest)
    else:
        return latest


def version_exists(data, target_version):
    is_found = False
    versions = data.getElementsByTagName("version")
    for version in versions:
        if version.firstChild.nodeValue == target_version:
            is_found = True
            break

    return is_found


def max_version_of(*args):
    def rank(ver):
        ver = ver or ""
        return [int(s) for s in ver.split(".") if s.isdigit()]

    return sorted(args, key=rank, reverse=True)[0]


def find_version_in(dom):
    latest = "latestRelease"
    try:
        data = dom.getElementsByTagName("artifact")[0]
        latest_node = data.getElementsByTagName(latest)[0]
    except:
        return None
    return latest_node.firstChild.nodeValue


def get_library_version_info_from_bintray(artifact):
    return get_maven_version_info_from_bintray("releases", artifact)


def get_sbt_plugin_version_info_from_bintray(artifact):
    return get_ivy_version_info_from_bintray("sbt-plugin-releases", artifact)


def get_ivy_version_info_from_bintray(repository_name, artifact):
    bintray = "https://api.bintray.com/packages/hmrc/" + repository_name + "/" + artifact
    print(bintray)
    request = url_request.Request(bintray)
    response = url_request.urlopen(request).read()
    return json.loads(response)['latest_version']


def get_maven_version_info_from_bintray(repository_name, artifact):
    bintray = "https://dl.bintray.com/hmrc/" + repository_name + "/uk/gov/hmrc/" + artifact + "/maven-metadata.xml"
    print(bintray)
    request = url_request.Request(bintray)
    response = url_request.urlopen(request)
    dom = parse(response)
    response.close()
    return dom


def lookup_credentials():
    sbt_credentials = os.environ["HOME"] + "/.sbt/.credentials"
    if not os.path.exists(sbt_credentials):
        print("Cannot look up nexus credentials from " + sbt_credentials)
        return {}
    return {key.strip(): value.strip() for (key, value) in
            map(lambda x: x.split("=", 1), open(sbt_credentials, 'r').readlines())}


def _header_credentials():
    credentials = lookup_credentials()
    return credentials["user"] + ":" + credentials["password"]


def replace_variables_for_app(application_root_name, folder_to_search, application_name, service_type, has_mongo=False):
    scala_version = "2.12.13"
    scala_binary_version = re.sub('\.(\d)*$', '', scala_version)
    print("scala_binary_version=" + scala_binary_version)
    if service_type == "FRONTEND":
        bootstrap_play_version = get_latest_library_version_in_open("bootstrap-frontend-play-28", scala_binary_version)
    elif service_type == "BACKEND":
        bootstrap_play_version = get_latest_library_version_in_open("bootstrap-backend-play-28", scala_binary_version)
    else:
        bootstrap_play_version = ""  # template won't use this

    play_frontend_hmrc_version = get_latest_library_version_in_open("play-frontend-hmrc", scala_binary_version)
    play_frontend_govuk_version = get_latest_library_version_in_open("play-frontend-govuk", scala_binary_version)
    play_language_version = get_latest_library_version_in_open("play-language", scala_binary_version)
    mongo_version = get_latest_library_version_in_open("mongo/hmrc-mongo-play-28", scala_binary_version)

    sbt_auto_build = get_latest_sbt_plugin_version_in_open("sbt-auto-build")
    sbt_git_versioning = get_latest_sbt_plugin_version_in_open("sbt-git-versioning")
    sbt_artifactory = get_latest_sbt_plugin_version_in_open("sbt-artifactory")
    sbt_distributables = get_latest_sbt_plugin_version_in_open("sbt-distributables")

    print("sbt_auto_build  " + sbt_auto_build)
    print("sbt_git_versioning  " + sbt_git_versioning)
    print("sbt_distributables  " + sbt_distributables)
    print("sbt_artifactory  " + sbt_artifactory)

    for subdir, dirs, files in os.walk(folder_to_search):
        if '.git' in dirs:
            dirs.remove('.git')

        for f in files:
            file_name = os.path.join(subdir, f)
            print("templating: " + subdir + " " + f)
            t = pyratemp.Template(filename=os.path.join(subdir, f))
            file_content = t(UPPER_CASE_APP_NAME=application_name.upper(),
                             UPPER_CASE_APP_NAME_UNDERSCORE_ONLY=application_name.upper().replace("-", "_"),
                             APP_NAME=application_name,
                             APP_PACKAGE_NAME=application_root_name.replace("-", ""),
                             SCALA_VERSION=scala_version,
                             type=service_type,
                             MONGO=has_mongo,
                             bootstrapPlayVersion=bootstrap_play_version,
                             playFrontendHmrcVersion=play_frontend_hmrc_version,
                             playFrontendGovukVersion=play_frontend_govuk_version,
                             playLanguageVersion=play_language_version,
                             mongoVersion=mongo_version,
                             sbt_auto_build=sbt_auto_build,
                             sbt_git_versioning=sbt_git_versioning,
                             sbt_distributables=sbt_distributables,
                             sbt_artifactory=sbt_artifactory,
                             bashbang="#!/bin/bash",
                             shbang="#!/bin/sh",
                             )
            write_to_file(file_name, file_content)


def write_to_file(f, file_content):
    open_file = open(f, 'w')
    open_file.write(file_content)
    open_file.close()


def replace_in_file(file_to_search, replace_this, with_this):
    for line in fileinput.input(file_to_search, inplace=True):
        print(line.replace(replace_this, with_this)),


def delete_files_for_type(project_folder, service_type):
    file_name = os.path.join(os.path.join(project_folder, "template"), "%s.delete" % service_type)
    for line in fileinput.input(file_name, inplace=False):
        file_name = os.path.join(project_folder, line).strip()
        if os.path.isfile(file_name):
            os.remove(file_name)
        if os.path.isdir(file_name):
            shutil.rmtree(file_name)


def call(command, quiet=True):
    if not quiet:
        print("calling: '" + command + "' from: '" + os.getcwd() + "'")
    ps_command = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ps_command.wait()
    return ps_command


def create_service(project_name, service_type, existing_repo, has_mongo, github_token):
    if service_type == "LIBRARY":
        template_dir = os.path.normpath(os.path.join(os.path.realpath(__file__), "../../../templates/library"))
    elif service_type in ["FRONTEND", "BACKEND"]:
        template_dir = os.path.normpath(os.path.join(os.path.realpath(__file__), "../../../templates/service"))
    else:
        raise Exception("ERROR: Invalid type '%s'" % service_type)

    print("project name :" + project_name)

    if existing_repo:
        clone_repo(project_name, github_token)

    print("Creating new service: %s, this could take a few moments" % project_name)
    project_folder = os.path.normpath(os.path.join(workspace, project_name))
    if os.path.isdir(project_folder) and not existing_repo:
        print("The folder '%s' already exists, not creating front end module" % str(project_folder))
    else:
        distutils.dir_util.copy_tree(template_dir, project_folder)
        replace_variables_for_app(project_name, project_folder, project_name, service_type, has_mongo)
        if service_type != "LIBRARY":
            delete_files_for_type(project_folder, service_type)
            shutil.rmtree(os.path.join(project_folder, "template"))
            move_folders_to_project_package(project_name, project_folder)
        print("Created %s at '%s'." % (service_type, project_folder))
        commit_repo(project_folder, project_name, existing_repo)
        if existing_repo:
            print("Pushing repo '%s'." % project_folder)
            push_repo(project_name)


def move_folders_to_project_package(project_root_name, project_folder):
    project_app_folder = "%s/app" % project_folder
    project_test_folder = "%s/test" % project_folder
    project_package = "uk/gov/hmrc/%s" % project_root_name.replace("-", "")
    project_package_app = os.path.join(project_app_folder, project_package)
    project_package_test = os.path.join(project_test_folder, project_package)

    package_app_dirs = os.listdir(project_app_folder)
    print(package_app_dirs)
    if 'assets' in package_app_dirs:
        package_app_dirs.remove('assets')

    move_files_to_dist(package_app_dirs, project_app_folder, project_package_app)
    move_files_to_dist(os.listdir(project_test_folder), project_test_folder, project_package_test)


def move_files_to_dist(dirs, src, dst):
    if not os.path.exists(dst):
        os.makedirs(dst)

    for d in dirs:
        full_path = src + "/" + d
        shutil.move(full_path, dst)


def clone_repo(repo, github_token):
    command = 'git clone https://%s@github.com/hmrc/%s' % (github_token, repo)
    print("cloning : " + command)
    ps_command = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, cwd=workspace)
    ps_command.communicate()
    if ps_command.returncode != 0:
        raise Exception("ERROR: Unable to clone repo '%s'" % repo)


def commit_repo(project_folder, project_name, existing_repo):
    os.chdir(project_folder)
    if not existing_repo:
        call('git init')
    call('git add . -A')
    call('git commit -m \"Creating new service %s\"' % project_name)


def push_repo(project_name):
    command = 'git push -u origin master'
    print("pushing repo : " + command)

    fnull = open(os.devnull, 'w')
    ps_command = subprocess.Popen(command, shell=True, stdout=fnull, stderr=fnull, cwd=workspace+'/'+project_name)
    ps_command.communicate()
    if ps_command.returncode != 0:
        raise Exception("ERROR: Unable to push repo '%s'" % project_name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Template Creation Tool - Create an new open service(s)... fast!')
    parser.add_argument('REPOSITORY', type=str, help='The name of the service you want to create')
    parser.add_argument('--type', choices=['FRONTEND', 'BACKEND', 'LIBRARY'], help='Sets the type of repository to be either a Play template for FRONTEND or BACKEND microservice or a Play library')
    parser.add_argument('--github-token', help='The github token authorised to push to the repository')
    parser.add_argument('--github', action='store_true', help='Does the repository already exists on github? Set --github for this repo to be cloned, and updated')
    parser.add_argument('--with-mongo', action='store_true', help='Does your service require Mongo? This only available if the repository is of type "BACKEND"')
    args = parser.parse_args()

    create_service(args.REPOSITORY, args.type, args.github, args.with_mongo, args.github_token)
