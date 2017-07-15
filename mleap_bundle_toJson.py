import glob
import json
import os
import shutil
import zipfile
import itertools
from pprint import pprint


# #######################################################################################
# ##  EXTRACTING BUNDLE DATA  ###########################################################
# #######################################################################################


def process_node(node_path, root_node=True):

    node_data = join_node_jsons(node_path)
    if node_data:
        if "op" in node_data and node_data["op"] == 'pipeline':
            subnodes = node_data["attributes"]["nodes"]["value"]
            parsed_subnodes = []
            for subnode in subnodes:
                parsed_subnode = process_node(os.path.join(node_path, "{}.node".format(subnode)), False)
                parsed_subnodes.append(parsed_subnode)
            node_data["stages"] = parsed_subnodes
            node_data.pop("attributes", None)
            node_data.pop("shape", None)
            node_data.pop("name", None)
            return node_data
        else:
            # Ensuring than pipelines with one stage keeps the json structure ...
            if root_node:
                wrapper = {"op": "pipeline", "stages": [node_data]}
                return wrapper
            return node_data
    else:
        return None


def join_node_jsons(node_path):
    try:
        node_filepath = os.path.join(node_path, NODE_FILE)
        model_filepath = os.path.join(node_path, MODEL_FILE)
        if os.path.isfile(node_filepath) and os.path.isfile(model_filepath):
            with open(node_filepath, encoding='utf-8') as node_file, \
                    open(model_filepath, encoding='utf-8') as model_file:
                model_data = json.loads(model_file.read())
                node_data = json.loads(node_file.read())
                # Join two dictionaries
                model_data.update(node_data)
            return model_data
        else:
            print("{} and/or {} don't exits".format(node_filepath,model_filepath))
            return None
    except Exception as e:
        return None


def remove_tmp_dir():
    # Remove temporary directory if exists
    if os.path.isdir(TEMP_DIR):
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


def process_bundle_zip(bundle_zip_path):

    # Remove temporary directory if exists
    remove_tmp_dir()

    try:
        # Extract zip file in temporal directory
        zip_ref = zipfile.ZipFile(bundle_zip_path, 'r')
        zip_ref.extractall(TEMP_DIR)
        zip_ref.close()

        # Checking if bundle.json file and root folder exits in temporal directory
        init_bundle_desc = os.path.join(TEMP_DIR, BUNDLE_FILE)
        init_root_folder = os.path.join(TEMP_DIR, ROOT_FOLDER)
        if os.path.isfile(init_bundle_desc) and os.path.isdir(init_root_folder):
            with open(init_bundle_desc, encoding='utf-8') as bundle_file:
                # Reading bundle model metadata -> bundle.json
                bundle_data = json.loads(bundle_file.read())
                # Initializing recursive process: navigating through nodes/folders collecting data
                root = process_node(init_root_folder)
                if root:
                    bundle_data.update(root)
                    return bundle_data
                print("{} - Bundle data has not been extracted correctly.".format(
                    os.path.basename(bundle_zip_path)
                ))
                return None
        else:
            print("Extracted zip file seems not to be a mleap serialized model.")
            return None
    except:
        return None
    finally:
        # Remove temporary directory if exists
        remove_tmp_dir()


# #######################################################################################
# ##  POST-PROCESSING BUNDLE DATA  ######################################################
# #######################################################################################

def get_bundle_inputs(bundle):
    inputs = []
    for stage in bundle["stages"]:
        if stage["op"] == 'pipeline':
            inputs.extend(get_bundle_inputs(stage))
        else:
            inputs.extend(get_stage_inputs(stage))
    return inputs


def get_bundle_outputs(bundle):
    output = []
    for stage in bundle["stages"]:
        if stage["op"] == 'pipeline':
            output.extend(get_bundle_outputs(stage))
        else:
            output.extend(get_stage_outputs(stage))
    return output


def get_stage_inputs(stage):
    inputs = []
    for s_input in stage["shape"]["inputs"]:
        inputs.append(s_input["name"])
    return inputs


def get_stage_outputs(stage):
    outputs = []
    for s_output in stage["shape"]["outputs"]:
        outputs.append(s_output["name"])
    return outputs


def get_stages_data(stage):
    stage_data = {
        "name": stage["op"],
        "inputs": get_stage_inputs(stage),
        "outputs": get_stage_outputs(stage)
    }
    return stage_data


def get_bundle_stages(bundle):
    stages = []
    for stage in bundle["stages"]:
        if stage["op"] == 'pipeline':
            stages.extend(get_bundle_stages(stage))
        else:
            stages.append(get_stages_data(stage))
    return stages


# #######################################################################################
# ##  GRAPHICS  #########################################################################
# #######################################################################################

# http://matthiaseisen.com/articles/graphviz/

import graphviz as gv
import functools

graph = functools.partial(gv.Graph, format='svg')
digraph = functools.partial(gv.Digraph, format='svg')


def add_nodes(graph, nodes):
    for n in nodes:
        if isinstance(n, tuple):
            graph.node(n[0], **n[1])
        else:
            graph.node(n)
    return graph


def add_edges(graph, edges):
    for e in edges:
        if isinstance(e[0], tuple):
            graph.edge(*e[0], **e[1])
        else:
            graph.edge(*e)
    return graph


def get_graph_data(stages):
    nodes = []  # ('A', {'label': 'Node A'})
    raw_edges = {}  # (('A', 'B'), {'label': 'Edge 1'})
    # {edge_name, (inputs[], outputs[]) }

    for idx, stage in enumerate(stages):
        stage_id = "{}_{}".format(idx, stage["name"])
        nodes.append((stage_id, {"label": stage_id}))
        for s_input in stage["inputs"]:
            if s_input in raw_edges:
                raw_edges[s_input][0].append(stage_id)
            else:
                raw_edges[s_input] = ([stage_id], [])

        for s_output in stage["outputs"]:
            if s_output in raw_edges:
                raw_edges[s_output][1].append(stage_id)
            else:
                raw_edges[s_output] = ([], [stage_id])

    edges = []
    for col_name, col_edges in raw_edges.items():
        for stage_source, stage_sink in itertools.product(col_edges[1], col_edges[0]):
            edges.append(((stage_source, stage_sink), {"label": col_name}))

    return nodes, edges


# #######################################################################################
# ##  MAIN FUNCTION  ####################################################################
# #######################################################################################

# Uncompressed bundle zip file components
BUNDLE_FILE = "bundle.json"
MODEL_FILE = "model.json"
NODE_FILE = "node.json"
ROOT_FOLDER = "root"

# Output folder
OUTPUT_FOLDER = "output"

# Temporal directory
TEMP_DIR = "/tmp/mleap_Bundle_uncompressed"

# Getting zip file included in serialized_bundles folder
bundlesDir = os.path.join(os.path.dirname(__file__), 'serialized_bundles')
zipFiles = glob.glob(bundlesDir + "/*.zip")

for zipFile in zipFiles:
    print("=> Processing file: {}".format(zipFile))

    # => Extracting bundle data
    bundle_data = process_bundle_zip(zipFile)

    if bundle_data:
        # => Saving bundle data (json) in output folder
        filePathNoExt, file_extension = os.path.splitext(zipFile)
        output_filename_NoExt = os.path.basename(filePathNoExt)
        with open('{}/{}.json'.format(OUTPUT_FOLDER, output_filename_NoExt), 'w') as outfile:
            json.dump(bundle_data, outfile, indent=4)

        # => Extracting information from bundle data

        # · All stages inputs
        inputs = get_bundle_inputs(bundle_data)

        # · All stages outputs
        outputs = get_bundle_outputs(bundle_data)

        # · Inputs of the dataframe: all stage inputs that are not created by them
        df_inputs = list(set(inputs) - set(outputs))

        # · Stages data: 'name' (stage order+type), 'inputs', 'outputs'
        stages_data = get_bundle_stages(bundle_data)

        # · Dataframe data
        dataframe_data = {
            "name": "dataframe",
            "inputs": [],
            "outputs": df_inputs
        }

        # · Getting information for building a graph
        dataframe_stages_data = [dataframe_data] + stages_data
        #pprint(dataframe_stages_data)

        graph_nodes, graph_edges = get_graph_data(dataframe_stages_data)
        print(graph_nodes)
        print(graph_edges)

        dot = add_edges(
             add_nodes(digraph(), graph_nodes),
             graph_edges
         )
        # Saving graph image
        dot.format = 'png'
        dot.render("{}/img/{}".format(OUTPUT_FOLDER, output_filename_NoExt))

 # sfdp -x -Goverlap=scale -Tpng g4 > data.png
 # neato -Tps g4 -o out.png
 # circo -Tpng g4 > data.png
