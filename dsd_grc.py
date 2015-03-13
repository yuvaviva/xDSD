#!/usr/bin/env python
##################################################
# Gnuradio Python Flow Graph
# Title: Dsd Grc
# Generated: Mon Mar  9 22:22:58 2015
##################################################

from gnuradio import analog
from gnuradio import eng_notation
from gnuradio import filter
from gnuradio import gr
from gnuradio import wxgui
from gnuradio.eng_option import eng_option
from gnuradio.fft import window
from gnuradio.filter import firdes
from gnuradio.wxgui import fftsink2
from gnuradio.wxgui import forms
from gnuradio.wxgui import scopesink2
from gnuradio.wxgui import waterfallsink2
from grc_gnuradio import wxgui as grc_wxgui
from optparse import OptionParser
import math
import osmosdr
import time
import wx

class dsd_grc(grc_wxgui.top_block_gui):

    def __init__(self):
        grc_wxgui.top_block_gui.__init__(self, title="Dsd Grc")

        ##################################################
        # Variables
        ##################################################
        self.xlate_offset_fine = xlate_offset_fine = 0
        self.target_freq = target_freq = 855462000
        self.samp_rate = samp_rate = 1000000
        self.samp_per_sym = samp_per_sym = 10
        self.decim = decim = 15
        self.center_freq = center_freq = 855700000
        self.xlate_bandwidth = xlate_bandwidth = 12500
        self.variable_static_text_0 = variable_static_text_0 = target_freq+xlate_offset_fine
        self.tuning_error = tuning_error = 0
        self.tune_offset = tune_offset = target_freq - center_freq
        self.pre_channel_rate = pre_channel_rate = samp_rate/decim
        self.gain = gain = 25
        self.channel_rate = channel_rate = 4800*samp_per_sym
        self.audio_mul = audio_mul = 0

        ##################################################
        # Blocks
        ##################################################
        _xlate_offset_fine_sizer = wx.BoxSizer(wx.VERTICAL)
        self._xlate_offset_fine_text_box = forms.text_box(
        	parent=self.GetWin(),
        	sizer=_xlate_offset_fine_sizer,
        	value=self.xlate_offset_fine,
        	callback=self.set_xlate_offset_fine,
        	label="Fine Offset",
        	converter=forms.float_converter(),
        	proportion=0,
        )
        self._xlate_offset_fine_slider = forms.slider(
        	parent=self.GetWin(),
        	sizer=_xlate_offset_fine_sizer,
        	value=self.xlate_offset_fine,
        	callback=self.set_xlate_offset_fine,
        	minimum=-10000,
        	maximum=10000,
        	num_steps=1000,
        	style=wx.SL_HORIZONTAL,
        	cast=float,
        	proportion=1,
        )
        self.Add(_xlate_offset_fine_sizer)
        _xlate_bandwidth_sizer = wx.BoxSizer(wx.VERTICAL)
        self._xlate_bandwidth_text_box = forms.text_box(
        	parent=self.GetWin(),
        	sizer=_xlate_bandwidth_sizer,
        	value=self.xlate_bandwidth,
        	callback=self.set_xlate_bandwidth,
        	label="Xlate BW",
        	converter=forms.float_converter(),
        	proportion=0,
        )
        self._xlate_bandwidth_slider = forms.slider(
        	parent=self.GetWin(),
        	sizer=_xlate_bandwidth_sizer,
        	value=self.xlate_bandwidth,
        	callback=self.set_xlate_bandwidth,
        	minimum=5000,
        	maximum=50000,
        	num_steps=1000,
        	style=wx.SL_HORIZONTAL,
        	cast=float,
        	proportion=1,
        )
        self.Add(_xlate_bandwidth_sizer)
        self._tuning_error_text_box = forms.text_box(
        	parent=self.GetWin(),
        	value=self.tuning_error,
        	callback=self.set_tuning_error,
        	label="Tuning Error",
        	converter=forms.float_converter(),
        )
        self.Add(self._tuning_error_text_box)
        self.nb = self.nb = wx.Notebook(self.GetWin(), style=wx.NB_TOP)
        self.nb.AddPage(grc_wxgui.Panel(self.nb), "BB-1")
        self.nb.AddPage(grc_wxgui.Panel(self.nb), "BB-2")
        self.nb.AddPage(grc_wxgui.Panel(self.nb), "Xlate-1")
        self.nb.AddPage(grc_wxgui.Panel(self.nb), "Xlate-2")
        self.nb.AddPage(grc_wxgui.Panel(self.nb), "4FSK")
        self.Add(self.nb)
        _gain_sizer = wx.BoxSizer(wx.VERTICAL)
        self._gain_text_box = forms.text_box(
        	parent=self.GetWin(),
        	sizer=_gain_sizer,
        	value=self.gain,
        	callback=self.set_gain,
        	label="Gain",
        	converter=forms.float_converter(),
        	proportion=0,
        )
        self._gain_slider = forms.slider(
        	parent=self.GetWin(),
        	sizer=_gain_sizer,
        	value=self.gain,
        	callback=self.set_gain,
        	minimum=0,
        	maximum=50,
        	num_steps=100,
        	style=wx.SL_HORIZONTAL,
        	cast=float,
        	proportion=1,
        )
        self.Add(_gain_sizer)
        self.wxgui_waterfallsink2_0_0 = waterfallsink2.waterfall_sink_c(
        	self.nb.GetPage(3).GetWin(),
        	baseband_freq=0,
        	dynamic_range=10,
        	ref_level=10,
        	ref_scale=2.0,
        	sample_rate=channel_rate,
        	fft_size=512,
        	fft_rate=15,
        	average=False,
        	avg_alpha=None,
        	title="Waterfall Plot",
        )
        self.nb.GetPage(3).Add(self.wxgui_waterfallsink2_0_0.win)
        self.wxgui_waterfallsink2_0 = waterfallsink2.waterfall_sink_c(
        	self.nb.GetPage(1).GetWin(),
        	baseband_freq=center_freq,
        	dynamic_range=100,
        	ref_level=50,
        	ref_scale=2.0,
        	sample_rate=samp_rate,
        	fft_size=512,
        	fft_rate=15,
        	average=False,
        	avg_alpha=None,
        	title="Waterfall Plot",
        	win=window.flattop,
        )
        self.nb.GetPage(1).Add(self.wxgui_waterfallsink2_0.win)
        self.wxgui_scopesink2_1 = scopesink2.scope_sink_f(
        	self.nb.GetPage(4).GetWin(),
        	title="Scope Plot",
        	sample_rate=channel_rate,
        	v_scale=1.5,
        	v_offset=0,
        	t_scale=0.05,
        	ac_couple=False,
        	xy_mode=False,
        	num_inputs=1,
        	trig_mode=wxgui.TRIG_MODE_AUTO,
        	y_axis_label="Counts",
        )
        self.nb.GetPage(4).Add(self.wxgui_scopesink2_1.win)
        self.wxgui_fftsink2_0_0 = fftsink2.fft_sink_c(
        	self.nb.GetPage(2).GetWin(),
        	baseband_freq=0,
        	y_per_div=10,
        	y_divs=10,
        	ref_level=0,
        	ref_scale=2.0,
        	sample_rate=channel_rate,
        	fft_size=1024,
        	fft_rate=30,
        	average=True,
        	avg_alpha=None,
        	title="FFT Plot",
        	peak_hold=False,
        	win=window.flattop,
        )
        self.nb.GetPage(2).Add(self.wxgui_fftsink2_0_0.win)
        def wxgui_fftsink2_0_0_callback(x, y):
        	self.set_0(x)
        
        self.wxgui_fftsink2_0_0.set_callback(wxgui_fftsink2_0_0_callback)
        self.wxgui_fftsink2_0 = fftsink2.fft_sink_c(
        	self.nb.GetPage(0).GetWin(),
        	baseband_freq=center_freq,
        	y_per_div=20,
        	y_divs=10,
        	ref_level=0,
        	ref_scale=2.0,
        	sample_rate=samp_rate,
        	fft_size=1024,
        	fft_rate=30,
        	average=True,
        	avg_alpha=None,
        	title="FFT Plot",
        	peak_hold=False,
        )
        self.nb.GetPage(0).Add(self.wxgui_fftsink2_0.win)
        def wxgui_fftsink2_0_callback(x, y):
        	self.set_target_freq(x)
        
        self.wxgui_fftsink2_0.set_callback(wxgui_fftsink2_0_callback)
        self._variable_static_text_0_static_text = forms.static_text(
        	parent=self.GetWin(),
        	value=self.variable_static_text_0,
        	callback=self.set_variable_static_text_0,
        	label="Final freq",
        	converter=forms.float_converter(),
        )
        self.Add(self._variable_static_text_0_static_text)
        self._target_freq_text_box = forms.text_box(
        	parent=self.GetWin(),
        	value=self.target_freq,
        	callback=self.set_target_freq,
        	label="Target freq",
        	converter=forms.float_converter(),
        )
        self.Add(self._target_freq_text_box)
        self.rational_resampler_xxx_0 = filter.rational_resampler_ccc(
                interpolation=pre_channel_rate,
                decimation=channel_rate,
                taps=None,
                fractional_bw=None,
        )
        self.osmosdr_source_0 = osmosdr.source( args="numchan=" + str(1) + " " + "" )
        self.osmosdr_source_0.set_sample_rate(samp_rate)
        self.osmosdr_source_0.set_center_freq(center_freq+tuning_error, 0)
        self.osmosdr_source_0.set_freq_corr(0, 0)
        self.osmosdr_source_0.set_dc_offset_mode(0, 0)
        self.osmosdr_source_0.set_iq_balance_mode(0, 0)
        self.osmosdr_source_0.set_gain_mode(False, 0)
        self.osmosdr_source_0.set_gain(14, 0)
        self.osmosdr_source_0.set_if_gain(gain, 0)
        self.osmosdr_source_0.set_bb_gain(gain, 0)
        self.osmosdr_source_0.set_antenna("", 0)
        self.osmosdr_source_0.set_bandwidth(0, 0)
          
        self.low_pass_filter_0 = filter.fir_filter_fff(1, firdes.low_pass(
        	1, channel_rate, 6000, 500, firdes.WIN_HAMMING, 6.76))
        self.freq_xlating_fir_filter_xxx_0 = filter.freq_xlating_fir_filter_ccc(decim, (firdes.low_pass(1, samp_rate, xlate_bandwidth/2, 3000)), tune_offset+xlate_offset_fine, samp_rate)
        _audio_mul_sizer = wx.BoxSizer(wx.VERTICAL)
        self._audio_mul_text_box = forms.text_box(
        	parent=self.GetWin(),
        	sizer=_audio_mul_sizer,
        	value=self.audio_mul,
        	callback=self.set_audio_mul,
        	label="Audio mul",
        	converter=forms.float_converter(),
        	proportion=0,
        )
        self._audio_mul_slider = forms.slider(
        	parent=self.GetWin(),
        	sizer=_audio_mul_sizer,
        	value=self.audio_mul,
        	callback=self.set_audio_mul,
        	minimum=-30,
        	maximum=10,
        	num_steps=40,
        	style=wx.SL_HORIZONTAL,
        	cast=float,
        	proportion=1,
        )
        self.Add(_audio_mul_sizer)
        self.analog_quadrature_demod_cf_0 = analog.quadrature_demod_cf(1.0)

        ##################################################
        # Connections
        ##################################################
        self.connect((self.analog_quadrature_demod_cf_0, 0), (self.low_pass_filter_0, 0))    
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.rational_resampler_xxx_0, 0))    
        self.connect((self.low_pass_filter_0, 0), (self.wxgui_scopesink2_1, 0))    
        self.connect((self.osmosdr_source_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))    
        self.connect((self.osmosdr_source_0, 0), (self.wxgui_fftsink2_0, 0))    
        self.connect((self.osmosdr_source_0, 0), (self.wxgui_waterfallsink2_0, 0))    
        self.connect((self.rational_resampler_xxx_0, 0), (self.analog_quadrature_demod_cf_0, 0))    
        self.connect((self.rational_resampler_xxx_0, 0), (self.wxgui_fftsink2_0_0, 0))    
        self.connect((self.rational_resampler_xxx_0, 0), (self.wxgui_waterfallsink2_0_0, 0))    


    def get_xlate_offset_fine(self):
        return self.xlate_offset_fine

    def set_xlate_offset_fine(self, xlate_offset_fine):
        self.xlate_offset_fine = xlate_offset_fine
        self._xlate_offset_fine_slider.set_value(self.xlate_offset_fine)
        self._xlate_offset_fine_text_box.set_value(self.xlate_offset_fine)
        self.set_variable_static_text_0(self.target_freq+self.xlate_offset_fine)
        self.freq_xlating_fir_filter_xxx_0.set_center_freq(self.tune_offset+self.xlate_offset_fine)

    def get_target_freq(self):
        return self.target_freq

    def set_target_freq(self, target_freq):
        self.target_freq = target_freq
        self.set_tune_offset(self.target_freq - self.center_freq)
        self.set_variable_static_text_0(self.target_freq+self.xlate_offset_fine)
        self._target_freq_text_box.set_value(self.target_freq)

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_pre_channel_rate(self.samp_rate/self.decim)
        self.wxgui_waterfallsink2_0.set_sample_rate(self.samp_rate)
        self.wxgui_fftsink2_0.set_sample_rate(self.samp_rate)
        self.freq_xlating_fir_filter_xxx_0.set_taps((firdes.low_pass(1, self.samp_rate, self.xlate_bandwidth/2, 3000)))
        self.osmosdr_source_0.set_sample_rate(self.samp_rate)

    def get_samp_per_sym(self):
        return self.samp_per_sym

    def set_samp_per_sym(self, samp_per_sym):
        self.samp_per_sym = samp_per_sym
        self.set_channel_rate(4800*self.samp_per_sym)

    def get_decim(self):
        return self.decim

    def set_decim(self, decim):
        self.decim = decim
        self.set_pre_channel_rate(self.samp_rate/self.decim)

    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, center_freq):
        self.center_freq = center_freq
        self.set_tune_offset(self.target_freq - self.center_freq)
        self.wxgui_waterfallsink2_0.set_baseband_freq(self.center_freq)
        self.wxgui_fftsink2_0.set_baseband_freq(self.center_freq)
        self.osmosdr_source_0.set_center_freq(self.center_freq+self.tuning_error, 0)

    def get_xlate_bandwidth(self):
        return self.xlate_bandwidth

    def set_xlate_bandwidth(self, xlate_bandwidth):
        self.xlate_bandwidth = xlate_bandwidth
        self._xlate_bandwidth_slider.set_value(self.xlate_bandwidth)
        self._xlate_bandwidth_text_box.set_value(self.xlate_bandwidth)
        self.freq_xlating_fir_filter_xxx_0.set_taps((firdes.low_pass(1, self.samp_rate, self.xlate_bandwidth/2, 3000)))

    def get_variable_static_text_0(self):
        return self.variable_static_text_0

    def set_variable_static_text_0(self, variable_static_text_0):
        self.variable_static_text_0 = variable_static_text_0
        self._variable_static_text_0_static_text.set_value(self.variable_static_text_0)

    def get_tuning_error(self):
        return self.tuning_error

    def set_tuning_error(self, tuning_error):
        self.tuning_error = tuning_error
        self._tuning_error_text_box.set_value(self.tuning_error)
        self.osmosdr_source_0.set_center_freq(self.center_freq+self.tuning_error, 0)

    def get_tune_offset(self):
        return self.tune_offset

    def set_tune_offset(self, tune_offset):
        self.tune_offset = tune_offset
        self.freq_xlating_fir_filter_xxx_0.set_center_freq(self.tune_offset+self.xlate_offset_fine)

    def get_pre_channel_rate(self):
        return self.pre_channel_rate

    def set_pre_channel_rate(self, pre_channel_rate):
        self.pre_channel_rate = pre_channel_rate

    def get_gain(self):
        return self.gain

    def set_gain(self, gain):
        self.gain = gain
        self._gain_slider.set_value(self.gain)
        self._gain_text_box.set_value(self.gain)
        self.osmosdr_source_0.set_if_gain(self.gain, 0)
        self.osmosdr_source_0.set_bb_gain(self.gain, 0)

    def get_channel_rate(self):
        return self.channel_rate

    def set_channel_rate(self, channel_rate):
        self.channel_rate = channel_rate
        self.wxgui_waterfallsink2_0_0.set_sample_rate(self.channel_rate)
        self.wxgui_fftsink2_0_0.set_sample_rate(self.channel_rate)
        self.wxgui_scopesink2_1.set_sample_rate(self.channel_rate)
        self.low_pass_filter_0.set_taps(firdes.low_pass(1, self.channel_rate, 6000, 500, firdes.WIN_HAMMING, 6.76))

    def get_audio_mul(self):
        return self.audio_mul

    def set_audio_mul(self, audio_mul):
        self.audio_mul = audio_mul
        self._audio_mul_slider.set_value(self.audio_mul)
        self._audio_mul_text_box.set_value(self.audio_mul)

if __name__ == '__main__':
    import ctypes
    import sys
    if sys.platform.startswith('linux'):
        try:
            x11 = ctypes.cdll.LoadLibrary('libX11.so')
            x11.XInitThreads()
        except:
            print "Warning: failed to XInitThreads()"
    parser = OptionParser(option_class=eng_option, usage="%prog: [options]")
    (options, args) = parser.parse_args()
    tb = dsd_grc()
    tb.Start(True)
    tb.Wait()
