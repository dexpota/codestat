from argparse import ArgumentParser
from functools import partial
from tempfile import mkdtemp
from shutil import rmtree
from subprocess import check_output
from operator import getitem
import subprocess
import os
import re
import json
import mmap
import yaml
import os.path

json_shema = "https://gist.githubusercontent.com/dexpota/5ef2064b4bc4c09b77811e06cfebd0ff/raw/schema.json"


def has_extension(filename, extensions):
    return filename.endswith(tuple(extensions))


def js_libraries(filename):
    jquery = re.match(r"jquery.*\.js", filename)
    bootstrap = re.match(r"bootstrap.*\.js", filename)
    # angular = re.match("angular.*\.js", filename)
    return not(jquery or bootstrap)


def and_function(foo, bar):
    def fuu(filename):
        if bar(filename) and foo(filename):
            print("js:", filename)
        return foo(filename) and bar(filename)
    return fuu


def mapcount(filename):
    try:
        f = open(filename, "r+")
        buf = mmap.mmap(f.fileno(), 0)
        lines = 0
        readline = buf.readline
        while readline():
            lines += 1
        return lines
    except ValueError:
        return 0


def count_lines(filename):
    return {"lines": mapcount(filename)}


def python_modules(filename):
    import re

    with open(filename) as fp:
        lines = fp.readlines()
        aaa = "".join(lines)
        matches = []
        matches += re.findall(r"^\s*import\s+([\.\w]+)\s*$", aaa, re.MULTILINE)
        matches += re.findall(r"^\s*from\s+([\.\w]+)\s+import\s+\w+\s*$", aaa, re.MULTILINE)
    return matches


def pip_search_module(module):
    try:
        import xmlrpc.client
    except ImportError:
        import xmlrpc.client as xmlrpclib

    client = xmlrpc.client.ServerProxy('https://pypi.python.org/pypi')
    # get a list of package names
    packages = client.list_packages()
    print("Module {} found: {}".format(module, module in packages))


def python_statistics(filename):
    lines = count_lines(filename)["lines"]
    modules = python_modules(filename)
    return {
        "lines": lines,
        "modules": modules
    }


def python_aggregate(statistics):
    cumulative_lines = 0
    modules_set = set()
    for statistic in statistics:
        if statistic["language"] == "Python":
            cumulative_lines += statistic["statistics"]["lines"]
            modules_set.update(statistic["statistics"]["modules"])
    return {
        "language": "Python",
        "statistics": {
            "lines": cumulative_lines,
            "modules": list(modules_set)
        }
    }


def build_file_statistics(local_path):
    pass


def build_statistics(root, path):
    statistics = []

    if os.path.isfile(os.path.join(root, "./" + path)):
        full_directory = os.path.join(root, "./" + path)
        filename = os.path.basename(full_directory)
        current_directory = os.path.dirname(full_directory)
        for l, obj in extensions_by_languages.items():
            if obj["filter"](filename):
                language_stats = {
                    "language": l,
                    "filename": filename,
                    "local_directory": "./{}".format(os.path.relpath(current_directory, root)),
                    "statistics": obj["statistics"](os.path.join(current_directory, filename))
                }
                statistics.append(language_stats)
                if l == "Python":
                    python_modules(os.path.join(current_directory, filename))
        return statistics

    for current_directory, dirnames, filenames in os.walk(os.path.join(root, path)):
        if ".git" in dirnames:
            dirnames.remove(".git")

        for filename in filenames:
            for l, obj in extensions_by_languages.items():
                if obj["filter"](filename):
                    language_stats = {
                        "language": l,
                        "filename": filename,
                        "local_directory": "./{}".format(os.path.relpath(current_directory, root)),
                        "statistics": obj["statistics"](os.path.join(current_directory, filename))
                    }
                    statistics.append(language_stats)
                    if l == "Python":
                        python_modules(os.path.join(current_directory, filename))


    return statistics


def is_git_directory(directory):
    if not os.path.isdir(os.path.join(directory, ".git")):
        return False

    try:
        check_output(["git", "rev-parse", "--is-inside-work-tree"])
        return True
    except Exception as e:
        return False

extensions_by_languages = {
    "C++": {
        "filter": partial(has_extension, extensions=["cpp", "hpp"]),
        "statistics": count_lines
    },

    "C": {
        "filter": partial(has_extension, extensions=["c", "h"]),
        "statistics": count_lines
    },

    "Python": {
        "filter": partial(has_extension, extensions=["py"]),
        "statistics": python_statistics,
        "aggregation": python_aggregate
    },

    "Java": {
        "filter": partial(has_extension, extensions=["java"]),
        "statistics": count_lines
    },

    "CMake": {
        "filter": lambda filename: filename == "CMakeLists.txt",
        "statistics": count_lines
    }
    # "Javascript": and_function(partial(has_extension, extensions=["js"]), js_libraries),
}

style_by_languages = {
    "C++": {"background-color": "#e6f9ff", "border-bottom-color": "#66d9ff"},
    "C": {"background-color": "#e6f2ff", "border-bottom-color": "#1a8cff"},
    "Python": {"background-color": "#ebfaeb", "border-bottom-color": "#33cc33"},
    "Java": {"background-color": "#f2e6ff", "border-bottom-color": "#8000ff"},
    # "Javascript": and_function(partial(has_extension, extensions=["js"]), js_libraries),
    "CMake": {"background-color": "#ffffcc", "border-bottom-color": "#ffff00"},
}


def main():
    repositories = []

    parser = ArgumentParser()
    parser.add_argument("statistics")
    parser.add_argument("--format", choices=["json"], default="json")
    parser.add_argument("--force", "-f", action="store_true", default=False)
    parser.add_argument("--validate", action="store_true", default=False)
    parser.add_argument("--directories", nargs="+", type=str)
    parser.add_argument("--repositories", nargs="+", type=str)
    parser.add_argument("--yaml", "--yml")
    args = parser.parse_args()

    if not args.directories and not args.repositories and not args.yaml:
        parser.error("at least one of --directories, --repositories, --yaml required")

    if args.repositories:
        repositories += args.repositories

    if args.yaml:
        try:
            repositories = []
            with open(args.yaml) as input_file:
                input_repositories = yaml.load(input_file)
                for key, value in input_repositories.items():
                    if "repository" in value:
                        repositories.append(value["repository"])
        except Exception:
            exit()

    force = args.force

    statistics_filename = args.statistics
    try:
        with open(statistics_filename, 'r') as outfile:
            repositories_statistics = json.load(outfile)
    except IOError as error:
        repositories_statistics = []

    regex = re.compile("([0-9a-fA-F]+)")
    for repository_path in repositories:
        pathname = mkdtemp()

        match = re.match(r"(((git|ssh|http(s)?)|(git@[\w\.]+))(:(//)?)([\w\.@\:/\-~]+)(\.git)(/)?):?(.*[^/]*)?", repository_path)
        if match:
            repository = match.groups()[0]
            local_directory = match.groups()[-1]

            if not local_directory:
                local_directory = "."
        else:
            continue

        ls_remote_output = check_output(["git", "ls-remote", repository, "HEAD"])
        head_hash = regex.match(ls_remote_output).group(0)

        try:
            index = map(lambda item: getitem(item, "repository"), repositories_statistics).index(repository)

            if force or repositories_statistics[index]["hashcode"] != head_hash:
                check_output(["git", "clone", repository, "."], cwd=pathname)
                repository_statistics = {
                    "repository": repository,
                    "statistics": build_statistics(pathname, local_directory),
                    "hashcode": head_hash
                }

                aggregations = []
                for l, obj in extensions_by_languages.items():
                    filtered = filter(lambda item: item["language"] == l, repository_statistics["statistics"])
                    if "aggregation" in obj and len(filtered):
                        aggregations.append(obj["aggregation"](repository_statistics["statistics"]))

                if len(aggregations):
                    repository_statistics["aggregation"] = aggregations

                repositories_statistics[index] = repository_statistics
        except ValueError as error:
            check_output(["git", "clone", repository, "."], cwd=pathname)
            repository_statistics = {
                "repository": repository,
                "statistics": build_statistics(pathname, "."),
                "hashcode": head_hash
            }

            aggregations = []
            for l, obj in extensions_by_languages.items():
                filtered = filter(lambda item: item["language"] == l, repository_statistics["statistics"])
                if "aggregation" in obj and len(filtered):
                    aggregations.append(obj["aggregation"](repository_statistics["statistics"]))

            if len(aggregations):
                repository_statistics["aggregation"] = aggregations

            repositories_statistics.append(repository_statistics)

        rmtree(pathname)

    if args.directories:
        for directory in args.directories:
            if is_git_directory(directory):
                ls_remote_output = subprocess.getoutput("git ls-remote " + directory + " HEAD")
                head_hash = regex.match(ls_remote_output).group(0)

                remote = subprocess.getoutput("git config --get remote.origin.url").lstrip().rstrip()
                try:
                    index = list(map(lambda item: getitem(item, "repository"), repositories_statistics)).index(remote)

                    if force or repositories_statistics[index]["hashcode"] != head_hash:
                        repository_statistics = {
                            "repository": remote,
                            "statistics": build_statistics(directory, "."),
                            "hashcode": head_hash
                        }

                        aggregations = []
                        for l, obj in extensions_by_languages.items():
                            filtered = filter(lambda item: item["language"] == l, repository_statistics["statistics"])
                            if "aggregation" in obj and len(filtered):
                                aggregations.append(obj["aggregation"](repository_statistics["statistics"]))

                        if len(aggregations):
                            repository_statistics["aggregation"] = aggregations

                        repositories_statistics[index] = repository_statistics
                except ValueError as error:
                    repository_statistics = {
                        "repository": remote,
                        "statistics": build_statistics(directory, "."),
                        "hashcode": head_hash
                    }

                    aggregations = []
                    for l, obj in list(extensions_by_languages.items()):
                        filtered = list(filter(lambda item: item["language"] == l, repository_statistics["statistics"]))
                        if "aggregation" in obj and len(filtered):
                            aggregations.append(obj["aggregation"](repository_statistics["statistics"]))

                    if len(aggregations):
                        repository_statistics["aggregation"] = aggregations

                    repositories_statistics.append(repository_statistics)

    global_statistics = dict(list(zip(list(extensions_by_languages.keys()), [{}]*len(extensions_by_languages))))

    #total_count = 0
    #for repository_statistics in repositories_statistics:
    #    for language, count in repository_statistics["statistics"].iteritems():
    #        global_statistics[language] += count
    #        total_count += count

    from string import Template
    style = "<style> " \
            ".language-box{ " \
            "text-align: center; font-weight: bold; border-bottom-style: solid; border-bottom-width: 10px; } " \
            "</style>"
    t = Template(
        "<span class='language-box' "
        "style='width: ${width}%; background-color: ${background_color}; border-bottom-color: ${border_bottom_color}'> "
        "${language} <span>(${lines})</span></span>")

    #for language, lines_of_code in global_statistics.iteritems():
    #    print t.substitute(language=language, width=float(lines_of_code) / total_count * 100,
    #                       lines=float(lines_of_code) / total_count * 100,
    #                       background_color=style_by_languages[language]["background-color"],
    #                       border_bottom_color=style_by_languages[language]["border-bottom-color"])

    with open(statistics_filename, 'w') as outfile:
        json.dump(repositories_statistics, outfile, indent=4, sort_keys=True)

    if args.validate:
        import urllib.request, urllib.error, urllib.parse
        import jsonschema
        response = urllib.request.urlopen(json_shema)
        schema = response.read()
        jsonschema.validate(repositories_statistics, json.loads(schema))

