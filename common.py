import os, traceback, sys, json, shutil
import subprocess32 as subprocess
from threading import Timer
from contextlib import contextmanager

WORKING_DIR = os.path.dirname(os.path.realpath(__file__))
LIBS_DIR = os.path.join(WORKING_DIR, "libs")
CORPUS_DIR = os.path.join(WORKING_DIR, "corpus")
CORPUS_INFO = None
TOOLS_DIR = os.path.join(WORKING_DIR, "tools")
SIMPROG_DIR = os.path.join(WORKING_DIR, "simprog")

CLUSTER_FILE = os.path.join(WORKING_DIR, "clusters.json")
CLASS2FIELDS_FILE = os.path.join(WORKING_DIR, "c2f.json")

DLJC_BINARY = os.path.join(TOOLS_DIR, "do-like-javac", "dljc")
DLJC_OUTPUT_DIR = "dljc-out"

DYNTRACE_ADDONS_DIR = os.path.join(WORKING_DIR, "dyntrace")

LIMITED_PROJECT_LIST = ["dyn4j", "jreactphysics3d", "jbox2d", "react", "jmonkeyengine"]

def run_cmd(cmd, print_output=False, timeout=None):
  def kill_proc(proc, stats):
    stats['timed_out'] = True
    proc.kill()

  stats = {'timed_out': False,
           'output': ''}
  timer = None

  if print_output:
    print ("Running %s" % ' '.join(cmd))
  try:
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    if timeout:
      timer = Timer(timeout, kill_proc, [process, stats])
      timer.start()

    for line in iter(process.stdout.readline, b''):
      stats['output'] = stats['output'] + line
      if print_output:
        sys.stdout.write(line)
        sys.stdout.flush()
    process.stdout.close()
    process.wait()
    stats['return_code'] = process.returncode
    if timer:
      timer.cancel()

  except:
    print ('calling {cmd} failed\n{trace}'.format(cmd=' '.join(cmd),trace=traceback.format_exc()))
  return stats

@contextmanager
def cd(newdir):
  prevdir = os.getcwd()
  os.chdir(os.path.expanduser(newdir))
  try:
    yield
  finally:
    os.chdir(prevdir)

def mkdir(newdir):
  if not os.path.isdir(newdir):
    os.makedirs(newdir)

def get_method_from_daikon_out(daikon_out):
  arr1 = daikon_out.split('.')
  arr2 = arr1[1].split(':::')
  method = arr2[0]
  return method

def get_jar(jar_name):
  path = os.path.join(LIBS_DIR, jar_name)
  if os.path.isfile(path):
    return path
  else:
    return None

def get_corpus_info():
  global CORPUS_INFO
  if not CORPUS_INFO:
    with open(os.path.join(WORKING_DIR, 'corpus.json')) as f:
      CORPUS_INFO = json.loads(f.read())

  return CORPUS_INFO

def get_project_dir(project_name):
  project = project_info(project_name)

  if 'build-dir' in project:
    return os.path.join(CORPUS_DIR, project['name'], project['build-dir'])
  else:
    return os.path.join(CORPUS_DIR, project['name'])

def get_project_list():
  return get_corpus_info()['projects'].keys()

def project_info(project_name):
  return get_corpus_info()['projects'][project_name]

def get_simprog(py_file):
  return os.path.join(SIMPROG_DIR, py_file)

def get_dljc_dir_for_project(project_name):
  dtrace_path = os.path.join(get_project_dir(project_name), DLJC_OUTPUT_DIR)
  if os.path.exists(dtrace_path):
    return dtrace_path
  else:
    return None

def clean_project(project_name):
  print "Cleaning {}".format(project_name)
  project_dir = get_project_dir(project_name)
  with cd(project_dir):
    clean_command = project_info(project_name)['clean'].strip().split()
    run_cmd(clean_command)
    run_cmd(['rm', '-r', DLJC_OUTPUT_DIR])

def get_class_dirs(project_name):
  classdirs = []

  dljc_output = os.path.join(get_project_dir(project_name),
                             DLJC_OUTPUT_DIR,
                             'javac.json')

  if not os.path.exists(dljc_output):
    print 'Tried to get classdirs from project where DLJC has not been run.'
    return None

  with open(dljc_output, 'r') as f:
    javac_commands = json.loads(f.read())
    for command in javac_commands:
      classdir = command['javac_switches'].get('d')
      if classdir:
        classdirs.append(classdir)

  return classdirs

def copy_dyntrace_files(project_name):
  project_dir = get_project_dir(project_name)
  out_dir = os.path.join(project_dir, DLJC_OUTPUT_DIR)
  mkdir(out_dir)
  addons = [f for f in os.listdir(DYNTRACE_ADDONS_DIR) \
            if f.startswith(project_info(project_name)['name']+".")]

  for addon in addons:
    addon_type = addon.rsplit('.', 1)[-1]
    shutil.copyfile(os.path.join(DYNTRACE_ADDONS_DIR, addon),
                    os.path.join(out_dir, addon_type))

def run_dljc(project_name, tools, options=[]):
  project = project_info(project_name)
  timelimit = project.get('timelimit') or 900

  copy_dyntrace_files(project_name)
  os.environ['DAIKONDIR'] = os.path.join(TOOLS_DIR, 'daikon-src')

  project_dir = get_project_dir(project_name)
  with cd(project_dir):
    build_command = project['build'].strip().split()
    dljc_command = [DLJC_BINARY,
                    '-l', LIBS_DIR,
                    '-o', DLJC_OUTPUT_DIR,
                    '-t', ','.join(tools),
                    '--timeout', str(timelimit)]
    dljc_command.extend(options)
    dljc_command.append('--')
    dljc_command.extend(build_command)
    run_cmd(dljc_command, print_output=True)

def ensure_java_home():
  if not os.environ.get('JAVA_HOME'):
    # If we're on OS X, we can auto-set JAVA_HOME
    if os.path.exists('/usr/libexec/java_home'):
      java_home = run_cmd(['/usr/libexec/java_home'])['output'].strip()
      print "Automatically setting JAVA_HOME to {}".format(java_home)
      os.environ['JAVA_HOME'] = java_home
    else:
      caller = inspect.stack()[1][3]
      print "ERROR: {} requires the JAVA_HOME environment variable to be set, and we couldn't set it automatically. Please set the JAVA_HOME environment variable and try again.".format(caller)
      sys.exit(0)

CHECKER_ENV_SETUP = False
def setup_checker_framework_env():
  global CHECKER_ENV_SETUP
  if CHECKER_ENV_SETUP:
    return

  jsr308 = TOOLS_DIR
  os.environ['JSR308'] = jsr308

  afu = os.path.join(jsr308, 'annotation-tools', 'annotation-file-utilities')
  os.environ['AFU'] = afu
  os.environ['PATH'] += ':' + os.path.join(afu, 'scripts')
  CHECKER_ENV_SETUP = True

def recompile_checker_framework():
  """ recompile checker framework stuffs
      include:
      - checker-framework-inference
      - ontology
  """
  ensure_java_home()
  checker_framework_inference_dir = os.path.join(TOOLS_DIR, "checker-framework-inference")
  ontology_dir = os.path.join(TOOLS_DIR, "ontology")

  with cd(checker_framework_inference_dir):
    setup_checker_framework_env()
    run_cmd(["gradle", "dist", "-i"], print_output=True)

  with cd(ontology_dir):
    setup_checker_framework_env()
    run_cmd(["gradle", "build", "-i"], print_output=True)
