#!/usr/bin/env python
""" 
	This program decodes the Motorola SmartNet II trunking protocol from the control channel
	Tune it to the control channel center freq, and it'll spit out the decoded packets.
	In what format? Who knows.

	This program does not include audio output support. It logs channels to disk by talkgroup name. If you don't specify what talkgroups to log, it logs EVERYTHING.
"""

from gnuradio import analog
from gnuradio import audio
from gnuradio import blocks
from gnuradio import eng_notation
from gnuradio import filter

from gnuradio.eng_option import eng_option
from gnuradio.filter import firdes
from optparse import OptionParser
import ConfigParser
import dsd
import math
import osmosdr
from gnuradio import gr, gru, blks2, optfir, digital





#from pkt import *
import time
import gnuradio.gr.gr_threading as _threading
import csv
import os

class top_block_runner(_threading.Thread):
    def __init__(self, tb):
        _threading.Thread.__init__(self)
        self.setDaemon(1)
        self.tb = tb
        self.done = False
        self.start()
        
    def run(self):
        self.tb.run()
        self.done = True

class my_top_block(gr.top_block):
	def __init__(self, options):
		gr.top_block.__init__(self)
		self.rate = options.rate
		
		print "Samples per second is %i" % self.rate

		self._syms_per_sec = 3600;

		options.audiorate = 44100
		options.rate = self.rate

		options.samples_per_second = self.rate #yeah i know it's on the list
		options.syms_per_sec = self._syms_per_sec
		options.gain_mu = 0.01
		options.mu=0.5
		options.omega_relative_limit = 0.3
		options.syms_per_sec = self._syms_per_sec
		options.offset = options.centerfreq - options.freq
		print "Tuning channel offset: %f" % options.offset


		self.freq = options.freq

		self.samp_rate = samp_rate = self.rate
		self.samp_per_sym = samp_per_sym = 10
		self.decim = decim = 20


		self.xlate_bandwidth = 14000
		self.pre_channel_rate = pre_channel_rate = int(samp_rate/decim)
		self.channel_rate = channel_rate = 4800*samp_per_sym
		
		self.rtl = osmosdr.source_c( args="nchan=" + str(1) + " " + ""  )
		self.rtl.set_sample_rate(options.rate)
		self.rtl.set_center_freq(options.centerfreq, 0)
		self.rtl.set_freq_corr(options.ppm, 0)
		#self.rtl.set_gain_mode(1, 0)
	
		print "Channel Rate: %d Pre Channel Rate: %d" % (channel_rate, pre_channel_rate)		

		self.centerfreq = options.centerfreq
		print "Setting center to (With Error): %fMHz" % (self.centerfreq - options.error)
		if not(self.tune(options.centerfreq - options.error)):
			print "Failed to set initial frequency"

		if options.gain is None: 
			options.gain = 14
		if options.bbgain is None: 
			options.bbgain = 25
		if options.ifgain is None: 
			options.ifgain = 25


		print "Setting RF gain to %i" % options.gain
		print "Setting BB gain to %i" % options.bbgain
		print "Setting IF gain to %i" % options.ifgain

		self.rtl.set_gain(options.gain, 0) 
		self.rtl.set_if_gain(options.ifgain,0)
		self.rtl.set_bb_gain(options.bbgain,0)
		
                

		self.freq_xlating_fir_filter_xxx_0 = filter.freq_xlating_fir_filter_ccc(decim, (firdes.low_pass(1, samp_rate, self.xlate_bandwidth/2, 6000)), -options.offset, samp_rate)
		self.fir_filter_xxx_0 = filter.fir_filter_fff(1, ((1.0/self.samp_per_sym,)*self.samp_per_sym))
		self.dsd_block_ff_0 = dsd.block_ff(dsd.dsd_FRAME_AUTO_DETECT,dsd.dsd_MOD_AUTO_SELECT,3,3,True)
		self.blks2_rational_resampler_xxx_1 = blks2.rational_resampler_ccc(
			interpolation=channel_rate,
			decimation=pre_channel_rate,
			taps=None,
			fractional_bw=None,
		)
		self.blks2_rational_resampler_xxx_0 = blks2.rational_resampler_fff(
			interpolation=44100,
			decimation=8000,
			taps=None,
			fractional_bw=None,
		)
		self.audio_sink_0 = audio.sink(44100, "", True)
		self.analog_quadrature_demod_cf_0 = analog.quadrature_demod_cf(1.6)
		
		#self.connect((self.blks2_rational_resampler_xxx_1, 0), (self.wxgui_fftsink2_0_0, 0))
		self.connect((self.blks2_rational_resampler_xxx_0, 0), (self.audio_sink_0, 0))
		self.connect((self.dsd_block_ff_0, 0), (self.blks2_rational_resampler_xxx_0, 0))
		
		#self.connect((self.analog_quadrature_demod_cf_0, 0), (self.dsd_block_ff_0, 0))
		self.connect((self.analog_quadrature_demod_cf_0, 0), (self.fir_filter_xxx_0, 0))
		self.connect((self.fir_filter_xxx_0, 0), (self.dsd_block_ff_0, 0))

		self.connect((self.rtl, 0), (self.freq_xlating_fir_filter_xxx_0, 0))
		self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.blks2_rational_resampler_xxx_1, 0))
		self.connect((self.blks2_rational_resampler_xxx_1, 0), (self.analog_quadrature_demod_cf_0, 0))
		
	def tune(self, freq):
		result = self.rtl.set_center_freq(freq)
		return True


def main():
	# Create Options Parser:
	parser = OptionParser (option_class=eng_option, conflict_handler="resolve")
	expert_grp = parser.add_option_group("Expert")

	parser.add_option("-f", "--freq", type="eng_float", default=866.9625e6,
						help="set control channel frequency to MHz [default=%default]", metavar="FREQ")
	parser.add_option("-c", "--centerfreq", type="eng_float", default=867.5e6,
						help="set center receive frequency to MHz [default=%default]. Set to center of 800MHz band for best results")
	parser.add_option("-g", "--gain", type="int", default=None,
						help="set RF gain", metavar="dB")
	parser.add_option("-i", "--ifgain", type="int", default=None,
						help="set IF gain", metavar="dB")
	parser.add_option("-b", "--bbgain", type="int", default=None,
						help="set BB gain", metavar="dB")
	parser.add_option("-r", "--rate", type="eng_float", default=64e6/18,
						help="set sample rate [default=%default]")
	parser.add_option("-C", "--chanlistfile", type="string", default=None,
						help="read in list of Motorola channel frequencies (improves accuracy of frequency decoding) [default=%default]")
	parser.add_option("-E", "--error", type="eng_float", default=5.5,
						help="enter an offset error to compensate for USRP clock inaccuracy")
	parser.add_option("-m", "--monitor", type="int", default=None,
						help="monitor a specific talkgroup")
	parser.add_option("-v", "--volume", type="eng_float", default=3.0,
						help="set volume gain for audio output [default=%default]")
	parser.add_option("-s", "--squelch", type="eng_float", default=28,
						help="set audio squelch level (default=%default, play with it)")
	parser.add_option("-D", "--directory", type="string", default="./log",
						help="choose a directory in which to save log data [default=%default]")

	parser.add_option("-p", "--ppm", type="eng_float", default=0,
						help="set RTL PPM frequency adjustment [default=%default]")

	

	(options, args) = parser.parse_args ()

	if len(args) != 0:
		parser.print_help(sys.stderr)
		sys.exit(1)


	if options.chanlistfile is not None:
		clreader=csv.DictReader(open(options.chanlistfile), quotechar='"')
		chanlist={"0": 0}
		for record in clreader:
			chanlist[record['channel']] = record['frequency']
	else:
		chanlist = None

	# build the graph
	queue = gr.msg_queue()
	tb = my_top_block(options)

	#tb.run(True)
	runner = top_block_runner(tb)

	updaterate = 10 #main loop rate in Hz


	try:
		while 1:
			time.sleep(1.0/updaterate)

	except KeyboardInterrupt:
		#perform cleanup: time to get out of Dodge

		tb.stop()

		runner = None

if __name__ == '__main__':
	main()


