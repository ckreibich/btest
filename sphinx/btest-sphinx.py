
import os
import os.path
import tempfile
import subprocess

from docutils import nodes, statemachine, utils
from docutils.parsers.rst import directives, Directive, DirectiveError, Parser
from docutils.transforms import TransformError, Transform
from sphinx.util.console import bold, purple, darkgreen, red, term_width_line
from sphinx.errors import SphinxError

Initialized = False
App = None
Reporter = None
BTestBase = None
BTestTests = None
BTestTmp = None

Tests = {}

def init(settings, reporter):
    global Intialized, App, Reporter, BTestBase, BTestTests, BTestTmp

    Initialized = True
    Reporter = reporter
    BTestBase = settings.env.config.btest_base
    BTestTests = settings.env.config.btest_tests
    BTestTmp = settings.env.config.btest_tmp

    if not BTestBase:
        raise SphinxError("error: btest_base not set in config")

    if not BTestTests:
        raise SphinxError("error: btest_tests not set in config")

    if not os.path.exists(BTestBase):
        raise SphinxError("error: btest_base directory '%s' does not exists" % BTestBase)

    joined = os.path.join(BTestBase, BTestTests)

    if not os.path.exists(joined):
        raise SphinxError("error: btest_tests directory '%s' does not exists" % joined)

    if not BTestTmp:
        BTestTmp = os.path.join(App.outdir, ".tmp/rst_output")

    BTestTmp = os.path.abspath(BTestTmp)

    if not os.path.exists(BTestTmp):
        os.makedirs(BTestTmp)

def parsePartial(rawtext, settings):
    parser = Parser()
    document = utils.new_document("<partial node>")
    document.settings = settings
    parser.parse(rawtext, document)
    return document.children

class Test(object):
    def __init__(self):
        self.has_run = False

    def run(self):
        if self.has_run:
            return

        App.builder.info("running test %s ..." % darkgreen(self.path))

        self.rst_output = os.path.join(BTestTmp, "%s" % self.tag)
        os.environ["BTEST_RST_OUTPUT"] = self.rst_output

        self.cleanTmps()

        try:
            subprocess.check_call("btest -qd %s" % self.path, shell=True)
        except (OSError, IOError, subprocess.CalledProcessError), e:
            # Equivalent to Directive.error(); we don't have an
            # directive object here and can't pass it in because
            # it doesn't pickle.
            App.builder.warn(red("BTest error: %s" % e))

    def cleanTmps(self):
        subprocess.call("rm %s#* 2>/dev/null" % self.rst_output, shell=True)

class BTestTransform(Transform):

    default_priority = 800

    def apply(self):
        pending = self.startnode
        (test, part) = pending.details

        os.chdir(BTestBase)

        if not test.tag in BTestTransform._run:
            test.run()
            BTestTransform._run.add(test.tag)

        try:
            rawtext = open("%s#%d" % (test.rst_output, part)).read()
        except IOError, e:
            rawtext = "BTest input error: %s" % e

        if len(rawtext):
            settings = self.document.settings
            content = parsePartial(rawtext, settings)
            pending.replace_self(content)
        else:
            pending.parent.parent.remove(pending.parent)

    _run = set()

class BTest(Directive):
    required_arguments = 1
    final_argument_whitespace = True
    has_content = True

    def error(self, msg):
        self.state.document.settings.env.note_reread()
        msg = red(msg)
        msg = self.state.document.reporter.error(str(msg), line=self.lineno)
        return [msg]

    def message(self, msg):
        Reporter.info(msg)

    def run(self):
        if not Initialized:
            # FIXME: Better way to handle one-time initialization?
            init(self.state.document.settings, self.state.document.reporter)

        os.chdir(BTestBase)

        self.assert_has_content()
        document = self.state_machine.document

        tag = self.arguments[0]

        if not tag in Tests:
            import sys
            test = Test()
            test.tag = tag
            test.path = os.path.join(BTestTests, tag + ".btest")
            test.parts = 0
            Tests[tag] = test

        test = Tests[tag]
        test.parts += 1
        part = test.parts

        # Save the test.

        if part == 1:
            file = test.path
        else:
            file = test.path + "#%d" % part

        out = open(file, "w")
        for line in self.content:
            print >>out, line

        out.close()

        details = (test, part)
        pending = nodes.pending(BTestTransform, details, rawsource=self.block_text)
        document.note_pending(pending)

        return [pending]

directives.register_directive('btest', BTest)

def setup(app):
    global App
    App = app

    app.add_config_value('btest_base', None, 'env')
    app.add_config_value('btest_tests', None, 'env')
    app.add_config_value('btest_tmp', None, 'env')
