# import sys, os
# path_prepend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# sys.path.append(path_prepend)
# from eventgenoutputtemplates import OutputTemplate

from __future__ import division
from outputplugin import OutputPlugin
import time
import os

class SpoolOutputPlugin(OutputPlugin):
    name = 'spool'
    MAXQUEUELENGTH = 10

    validSettings = [ 'spoolDir', 'spoolFile' ]
    defaultableSettings = [ 'spoolDir', 'spoolFile' ]

    _spoolDir = None
    _spoolFile = None

    def __init__(self, sample):
        OutputPlugin.__init__(self, sample)
        self._spoolDir = sample.pathParser(sample.spoolDir)
        self._spoolFile = sample.spoolFile
        self.spoolPath = self._spoolDir + os.sep + self._spoolFile

    def flush(self, q):
        if len(q) > 0:

            self.logger.debug("Flushing output for sample '%s' in app '%s' for queue '%s'" % (self._sample.name, self._app, self._sample.source))
            # Keep trying to open destination file as it might be touched by other processes
            while True:
                try:
                    with open(self.spoolPath, 'a') as dst:
                        for metamsg in q:
                            msg = metamsg['_raw']
                            if msg:
                                dst.write(msg)
                    break
                except:
                    time.sleep(0.1)
            self.logger.debug("Queue for app '%s' sample '%s' written" % (self._app, self._sample.name))


def load():
    """Returns an instance of the plugin"""
    return SpoolOutputPlugin
