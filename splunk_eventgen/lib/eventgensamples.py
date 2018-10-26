# TODO Move config settings to plugins

from __future__ import division, with_statement
import os, sys
import logging
import pprint
import datetime
import re
import csv
import copy
import urllib
from timeparser import timeParser


class Sample(object):
    """
    The Sample class is the primary configuration holder for Eventgen.  Contains all of our configuration
    information for any given sample, and is passed to most objects in Eventgen and a copy is maintained
    to give that object access to configuration information.  Read and configured at startup, and each
    object maintains a threadsafe copy of Sample.
    """
    # Required fields for Sample
    name = None
    app = None
    filePath = None
    
    # Options which are all valid for a sample
    disabled = None
    spoolDir = None
    spoolFile = None
    breaker = None
    sampletype = None
    mode = None
    interval = None
    delay = None
    count = None
    bundlelines = None
    earliest = None
    latest = None
    hourOfDayRate = None
    dayOfWeekRate = None
    randomizeEvents = None
    randomizeCount = None
    outputMode = None
    fileName = None
    fileMaxBytes = None
    fileBackupFiles = None
    splunkHost = None
    splunkPort = None
    splunkMethod = None
    splunkUser = None
    splunkPass = None
    index = None
    source = None
    sourcetype = None
    host = None
    hostRegex = None
    hostToken = None
    tokens = None
    projectID = None
    accessToken = None
    backfill = None
    backfillSearch = None
    backfillSearchUrl = None
    minuteOfHourRate = None
    timeMultiple = None
    debug = None
    timezone = datetime.timedelta(days=1)
    dayOfMonthRate = None
    monthOfYearRate = None
    sessionKey = None
    splunkUrl = None
    generator = None
    rater = None
    timeField = None
    timestamp = None
    sampleDir = None
    backfillts = None
    backfilldone = None
    stopping = False
    maxIntervalsBeforeFlush = None
    maxQueueLength = None
    end = None
    queueable = None
    autotimestamp = None

    
    # Internal fields
    sampleLines = None
    sampleDict = None
    _lockedSettings = None
    _priority = None
    _origName = None
    _lastts = None
    _earliestParsed = None
    _latestParsed = None
    
    def __init__(self, name):
        self.name = name
        self.tokens = [ ]
        self._lockedSettings = [ ]
        self.backfilldone = False
        self._setup_logging()

    def updateConfig(self, config):
        self.config = config

    def __str__(self):
        """Only used for debugging, outputs a pretty printed representation of this sample"""
        filter_list = [ 'sampleLines', 'sampleDict' ]
        temp = dict([ (key, value) for (key, value) in self.__dict__.items() if key not in filter_list ])
        return pprint.pformat(temp)
        
    def __repr__(self):
        return self.__str__()

    # loggers can't be pickled due to the lock object, remove them before we try to pickle anything.
    def __getstate__(self):
        temp = copy.copy(self.__dict__)
        if getattr(self, 'logger', None):
            temp.pop('logger', None)
        return temp

    def __setstate__(self, d):
        self.__dict__ = d
        self._setup_logging()

    def _setup_logging(self):
        logger = logging.getLogger('eventgen')
        self.logger = logger

    ## Replaces $SPLUNK_HOME w/ correct pathing
    def pathParser(self, path):
        greatgreatgrandparentdir = os.path.dirname(os.path.dirname(self.config.grandparentdir))
        sharedStorage = ['$SPLUNK_HOME/etc/apps', '$SPLUNK_HOME/etc/users/', '$SPLUNK_HOME/var/run/splunk']

        ## Replace windows os.sep w/ nix os.sep
        path = path.replace('\\', '/')
        ## Normalize path to os.sep
        path = os.path.normpath(path)

        ## Iterate special paths
        for x in range(0, len(sharedStorage)):
            sharedPath = os.path.normpath(sharedStorage[x])

            if path.startswith(sharedPath):
                path.replace('$SPLUNK_HOME', greatgreatgrandparentdir)
                break

        ## Split path
        path = path.split(os.sep)

        ## Iterate path segments
        for x in range(0, len(path)):
            segment = path[x].lstrip('$')
            ## If segement is an environment variable then replace
            if os.environ.has_key(segment):
                path[x] = os.environ[segment]

        ## Join path
        path = os.sep.join(path)

        return path

    # 9/2/15 Adding ability to pass in a token rather than using the tokens from the sample
    def getTSFromEvent(self, event, passed_token=None):
        currentTime = None
        formats = [ ]
        # JB: 2012/11/20 - Can we optimize this by only testing tokens of type = *timestamp?
        # JB: 2012/11/20 - Alternatively, documentation should suggest putting timestamp as token.0.
        if passed_token != None:
            tokens = [ passed_token ]
        else:
            tokens = self.tokens
        for token in tokens:
            try:
                formats.append(token.token)
                # self.logger.debug("Searching for token '%s' in event '%s'" % (token.token, event))
                results = token._search(event)
                if results:
                    timeFormat = token.replacement
                    group = 0 if len(results.groups()) == 0 else 1
                    timeString = results.group(group)
                    # self.logger.debug("Testing '%s' as a time string against '%s'" % (timeString, timeFormat))
                    if timeFormat == "%s":
                        ts = float(timeString) if len(timeString) < 10 else float(timeString) / (10**(len(timeString)-10))
                        # self.logger.debugv("Getting time for timestamp '%s'" % ts)
                        currentTime = datetime.datetime.fromtimestamp(ts)
                    else:
                        # self.logger.debugv("Getting time for timeFormat '%s' and timeString '%s'" % (timeFormat, timeString))
                        # Working around Python bug with a non thread-safe strptime.  Randomly get AttributeError
                        # when calling strptime, so if we get that, try again
                        while currentTime == None:
                            try:
                                # Checking for timezone adjustment
                                if timeString[-5] == "+":
                                    timeString = timeString[:-5]
                                currentTime = datetime.datetime.strptime(timeString, timeFormat)
                            except AttributeError:
                                pass
                    self.logger.debugv("Match '%s' Format '%s' result: '%s'" % (timeString, timeFormat, currentTime))
                    if type(currentTime) == datetime.datetime:
                        break
            except ValueError:
                self.logger.warning("Match found ('%s') but time parse failed. Timeformat '%s' Event '%s'" % (timeString, timeFormat, event))
        if type(currentTime) != datetime.datetime:
            # Total fail
            if passed_token == None: # If we're running for autotimestamp don't log error
                self.logger.warning("Can't find a timestamp (using patterns '%s') in this event: '%s'." % (formats, event))
            raise ValueError("Can't find a timestamp (using patterns '%s') in this event: '%s'." % (formats, event))
        # Check to make sure we parsed a year
        if currentTime.year == 1900:
            currentTime = currentTime.replace(year=self.now().year)
        # 11/3/14 CS So, this is breaking replay mode, and getTSFromEvent is only used by replay mode
        #            but I don't remember why I added these two lines of code so it might create a regression.
        #            Found the change on 6/14/14 but no comments as to why I added these two lines.
        # if self.timestamp == None:
        #     self.timestamp = currentTime
        return currentTime
    
    def saveState(self):
        """Saves state of all integer IDs of this sample to a file so when we restart we'll pick them up"""
        for token in self.tokens:
            if token.replacementType == 'integerid':
                stateFile = open(os.path.join(self.sampleDir, 'state.'+urllib.pathname2url(token.token)), 'w')
                stateFile.write(token.replacement)
                stateFile.close()

    def now(self, utcnow=False, realnow=False):
        # self.logger.info("Getting time (timezone %s)" % (self.timezone))
        if not self.backfilldone and not self.backfillts == None and not realnow:
            return self.backfillts
        elif self.timezone.days > 0:
            return datetime.datetime.now()
        else:
            return datetime.datetime.utcnow() + self.timezone

    def get_backfill_time(self, current_time):
        if not current_time:
            current_time = self.now()
        if not self.backfill:
            return current_time
        else:
            if self.backfill[0] == '-':
                backfill_time = self.backfill[1:-1]
                if self.backfill[-2:] == 'ms':
                    backfill_time = self.backfill[1:-2]
                    return current_time - datetime.timedelta(milliseconds=int(backfill_time))
                elif self.backfill[-1] == 's':
                    return current_time - datetime.timedelta(seconds=int(backfill_time))
                elif self.backfill[-1] == 'm':
                    return current_time - datetime.timedelta(minutes=int(backfill_time))
                elif self.backfill[-1] == 'h':
                    return current_time - datetime.timedelta(hours=int(backfill_time))
                elif self.backfill[-1] == 'd':
                    return current_time - datetime.timedelta(days=int(backfill_time))
        return current_time


    def earliestTime(self):
        # First optimization, we need only store earliest and latest
        # as an offset of now if they're relative times
        if self._earliestParsed != None:
            earliestTime = self.now() - self._earliestParsed
            self.logger.debugv("Using cached earliest time: %s" % earliestTime)
        else:
            if self.earliest.strip()[0:1] == '+' or \
                    self.earliest.strip()[0:1] == '-' or \
                    self.earliest == 'now':
                tempearliest = timeParser(self.earliest, timezone=self.timezone)
                temptd = self.now(realnow=True) - tempearliest
                self._earliestParsed = datetime.timedelta(days=temptd.days, seconds=temptd.seconds)
                earliestTime = self.now() - self._earliestParsed
                self.logger.debugv("Calulating earliestParsed as '%s' with earliestTime as '%s' and self.sample.earliest as '%s'" % (self._earliestParsed, earliestTime, tempearliest))
            else:
                earliestTime = timeParser(self.earliest, timezone=self.timezone)
                self.logger.debugv("earliestTime as absolute time '%s'" % earliestTime)

        return earliestTime


    def latestTime(self):
        if self._latestParsed != None:
            latestTime = self.now() - self._latestParsed
            self.logger.debugv("Using cached latestTime: %s" % latestTime)
        else:
            if self.latest.strip()[0:1] == '+' or \
                    self.latest.strip()[0:1] == '-' or \
                    self.latest == 'now':
                templatest = timeParser(self.latest, timezone=self.timezone)
                temptd = self.now(realnow=True) - templatest
                self._latestParsed = datetime.timedelta(days=temptd.days, seconds=temptd.seconds)
                latestTime = self.now() - self._latestParsed
                self.logger.debugv("Calulating latestParsed as '%s' with latestTime as '%s' and self.sample.latest as '%s'" % (self._latestParsed, latestTime, templatest))
            else:
                latestTime = timeParser(self.latest, timezone=self.timezone)
                self.logger.debugv("latstTime as absolute time '%s'" % latestTime)

        return latestTime

    def utcnow(self):
        return self.now(utcnow=True)

    def _openSampleFile(self):
        self.logger.debugv("Opening sample '%s' in app '%s'" % (self.name, self.app))
        self._sampleFH = open(self.filePath, 'rU')

    def _closeSampleFile(self):
        self.logger.debugv("Closing sample '%s' in app '%s'" % (self.name, self.app))
        self._sampleFH.close()

    def loadSample(self):
        if not self.logger:
            self._setup_logging()
        """Load sample from disk into self._sample.sampleLines and self._sample.sampleDict, 
        using cached copy if possible"""
        if self.sampletype == 'raw':
            # 5/27/12 CS Added caching of the sample file
            if self.sampleDict == None:
                self._openSampleFile()
                if self.breaker == self.config.breaker:
                    self.logger.debugv("Reading raw sample '%s' in app '%s'" % (self.name, self.app))
                    self.sampleLines = self._sampleFH.readlines()
                # 1/5/14 CS Moving to using only sampleDict and doing the breaking up into events at load time instead of on every generation
                else:
                    self.logger.debugv("Non-default breaker '%s' detected for sample '%s' in app '%s'" \
                                    % (self.breaker, self.name, self.app) ) 

                    sampleData = self._sampleFH.read()
                    self.sampleLines = [ ]

                    self.logger.debug("Filling array for sample '%s' in app '%s'; sampleData=%s, breaker=%s" \
                                    % (self.name, self.app, len(sampleData), self.breaker))

                    try:
                        breakerRE = re.compile(self.breaker, re.M)
                    except:
                        self.logger.error("Line breaker '%s' for sample '%s' in app '%s' could not be compiled; using default breaker" \
                                    % (self.breaker, self.name, self.app) )
                        self.breaker = self.config.breaker

                    # Loop through data, finding matches of the regular expression and breaking them up into
                    # "lines".  Each match includes the breaker itself.
                    extractpos = 0
                    searchpos = 0
                    breakerMatch = breakerRE.search(sampleData, searchpos)
                    while breakerMatch:
                        self.logger.debugv("Breaker found at: %d, %d" % (breakerMatch.span()[0], breakerMatch.span()[1]))
                        # Ignore matches at the beginning of the file
                        if breakerMatch.span()[0] != 0:
                            self.sampleLines.append(sampleData[extractpos:breakerMatch.span()[0]])
                            extractpos = breakerMatch.span()[0]
                        searchpos = breakerMatch.span()[1]
                        breakerMatch = breakerRE.search(sampleData, searchpos)
                    self.sampleLines.append(sampleData[extractpos:])

                self._closeSampleFile()
                self.sampleDict = []
                for line in self.sampleLines:
                    if line and line[-1] != '\n':
                        line = line + '\n'
                    self.sampleDict.append({ '_raw': line, 'index': self.index, 'host': self.host, 'source': self.source, 'sourcetype': self.sourcetype })
                self.logger.debug('Finished creating sampleDict & sampleLines.  Len samplesLines: %d Len sampleDict: %d' % (len(self.sampleLines), len(self.sampleDict)))
        elif self.sampletype == 'csv':
            if self.sampleDict == None:
                self._openSampleFile()
                self.logger.debugv("Reading csv sample '%s' in app '%s'" % (self.name, self.app))
                self.sampleDict = [ ]
                self.sampleLines = [ ]
                # Fix to load large csv files, work with python 2.5 onwards
                csv.field_size_limit(sys.maxint)
                csvReader = csv.DictReader(self._sampleFH)
                for line in csvReader:
                    if '_raw' in line:
                        self.sampleDict.append(line)
                        self.sampleLines.append(line['_raw'])
                    else:
                        self.logger.error("Missing _raw in line '%s'" % pprint.pformat(line))
                self._closeSampleFile()
                self.logger.debug("Finished creating sampleDict & sampleLines for sample '%s'.  Len sampleDict: %d" % (self.name, len(self.sampleDict)))

                for i in xrange(0, len(self.sampleDict)):
                    if len(self.sampleDict[i]['_raw']) < 1 or self.sampleDict[i]['_raw'][-1] != '\n':
                        self.sampleDict[i]['_raw'] += '\n'

    def get_loaded_sample(self):
        if self.sampletype != 'csv' and os.path.getsize(self.filePath) > 10000000 :
            self._openSampleFile()
            return self._sampleFH
        elif self.sampletype == 'csv':
            self.loadSample()
            return self.sampleDict
        else:
            self.loadSample()
            return self.sampleLines




