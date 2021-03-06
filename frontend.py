import sys, os, shutil

import inv_check
import insert_jaif
import ontology_to_daikon
import pa2checker

import backend
import common
import dot
import argparse
from simprog import Similarity
import json

def get_daikon_patterns():
  ordering_operator = "<="

  ontology_invariant_file = "TODO_from_Howie.txt"
  with open(ontology_invariant_file, 'w') as f:
    f.write(ordering_operator)

  invariant_name = "TODO_sorted_sequence"

  daikon_pattern_java_file = ontology_to_daikon.create_daikon_invariant(ontology_invariant_file, invariant_name)

  pattern_class_dir = os.path.join(common.WORKING_DIR, "invClass")
  if os.path.isdir(pattern_class_dir):
    shutil.rmtree(pattern_class_dir)
  os.mkdir(pattern_class_dir)

  cmd = ["javac", "-g", "-classpath", common.get_jar('daikon.jar'),
         daikon_pattern_java_file, "-d", pattern_class_dir]
  common.run_cmd(cmd)

  return pattern_class_dir


def compute_daikon_invariants(project_list, pattern_class_dir=None):

  list_of_methods = []
  for project in project_list:

    dljc_dir = common.get_dljc_dir_for_project(project)
    if (not dljc_dir) or (not os.path.isdir(dljc_dir)):
      print ("Project {0} was not built".format(project))
      continue
    i=0
    while True:
      i+=1
      dtrace_dir = os.path.join(dljc_dir, "test-classes{}".format(i))
      dtrace_file = os.path.join(dtrace_dir, 'RegressionTestDriver.dtrace.gz')
      if not os.path.isfile(dtrace_file):
        print ("No dtrace file found at {0}".format(dtrace_file))
        break
    
      ppt_names = inv_check.find_ppts_that_establish_inv(dtrace_file, pattern_class_dir, "TODO_sorted_sequence")
      methods = set()
      for ppt in ppt_names:
        print ("BINGO !!!!!!!!!!! {0}".format(ppt))
        method_name = ppt[:ppt.find(':::EXIT')]
        methods.add(method_name)
      list_of_methods +=[(project, methods)]

  print ("\n   ************")
  print ("The following corpus methods return a sequence sorted by <=")
  for project, methods in list_of_methods:
    if len(methods)>0:
      print (project)
      for m in methods:
        print("\t{}".format(m))
  print ("\n   ************")

  if pattern_class_dir:
    shutil.rmtree(pattern_class_dir)

def get_method_map(project_list):
  dot_to_method_map = {}
  for project in project_list:
    for output_dir in dot.dot_dirs(project):
      #output_dir = dot.dot_dirs(project)[0] # first folder only for now
      method_file = dot.get_method_path(project, output_dir)
      if not os.path.isfile(method_file):
        print ("Cannot find method file for project {0} at {1}".format(project, method_file))
        sys.exit(0)

      with open(method_file, "r") as mf:
        content = mf.readlines()
        for line in content:
          line = line.rstrip()
          items = line.split('\t')
          method_name = items[0]
          method_dot = items[1]
          method_dot_path = dot.get_dot_path(project, output_dir, method_dot)          
          dot_to_method_map[method_dot_path] = method_name
  return dot_to_method_map

def check_similarity(project, result_file, kernel_file, corpus_dot_to_method_map, output_json_file, cluster_json=None, top_k=5):
  """ SUMMARY: use case of the user-driven functionality of PASCALI.
  """

  # fetch various method information from each project in the list
  # output_dir = dot.dot_dirs(project)[0]
  # method_file = dot.get_method_path(project, output_dir)

  # check similarity
  json_result = {}
  sim = Similarity()
  sim.read_graph_kernels(kernel_file)
  iter_num = 3 # number of iteration of the WL-Kernel method
  this_method_map = get_method_map([project])
  with open(result_file, "w") as fo:    
    for dot_file in this_method_map.keys():
      dot_method = corpus_dot_to_method_map[dot_file]
      json_result[dot_method] = []
      result_program_list_with_score = sim.find_top_k_similar_graphs(dot_file, dot_file, top_k, iter_num, cluster_json)
      line = dot_file+":\n"
      for (dt, score) in result_program_list_with_score:
        line += "{} , {}\n".format(dt, score)
        if dt not in corpus_dot_to_method_map:
          print("{0} does not exist.".format(dt))
          sys.exit(0)
      tmp_dict = {}
      tmp_dict[corpus_dot_to_method_map[dt]] = score
      json_result[dot_method].append(tmp_dict)
      line += "\n"
      fo.write(line)
  with open(output_json_file, "w") as jo:
    jo.write(json.dumps(json_result, indent=4))

def run(project_list, args, kernel_dir):
  dot_method_map = get_method_map(project_list)
  for project in project_list:
    print("Computing similar programs for {0}...".format(project))
    result_file = os.path.join(common.WORKING_DIR, args.dir, project+"_result.txt")
    kernel_file = os.path.join(common.WORKING_DIR, kernel_dir, project+"_kernel.txt")
    json_file = os.path.join(common.WORKING_DIR, args.dir, project+"_result.json") 
    check_similarity(project, result_file, kernel_file, dot_method_map, json_file, args.cluster, min(5,len(project_list)))

    #compute_daikon_invariants(project_list, get_daikon_patterns())
    #compute_daikon_invariants(project_list)

