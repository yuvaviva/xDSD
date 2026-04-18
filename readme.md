 *Copyright 2012 Clayton Smith*

 *This file is part of gr-dsd*

*gr-dsd is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 3, or (at your option)
any later version.*

*gr-dsd is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.*

*You should have received a copy of the GNU General Public License
along with gr-dsd; see the file COPYING.  If not, write to
the Free Software Foundation, Inc., 51 Franklin Street,
Boston, MA 02110-1301, USA.*

#gr-dsd

**Author: Clayton Smith**

**Email: <argilo@gmail.com>**

The goal of this project is to package Digital Speech Decoder (DSD) as
a GNU Radio block, so that it can be easily used with software radio
peripherals such as the Ettus Research USRP or RTL2832U-based USB TV
tuners.

Note that it is still in an early stage of development.  Not all of
DSD's configuration options are exposed yet.  I have only tested on
Ubuntu 12.04 64-bit with GNU Radio 3.6.1, so please let me know if you
have any trouble building and running it.

Build instructions:

    cmake .
    make
    sudo make install
    sudo ldconfig

After running the above commands, "DSD Block" should appear under the
"DSD" category in GNU Radio Companion, and "block_ff" will be available
in the "dsd" Python package.

The block expects 48000 samples per second input, and outputs sound at
8000 samples per second.  The input should be FM-demodulated (for
example, with GNU Radio's Quadrature Demod block) and should be between
-1 and 1 while receiving digital signals.  (A quadrature demod gain of
1.6 works well for me for EDACS Provoice.)  The input signal should
also be free of DC bias, so make sure you are tuned accurately, or
filter out DC.

To save CPU cycles, the block detects when the input is zero and avoids
sending it through DSD.  Thus it helps to put a squelch block before
gr-dsd, especially if you're using many copies of gr-dsd in parallel.

The underlying DSD and mbelib were taken from:

    https://github.com/szechyjs/dsd
    https://github.com/szechyjs/mbelib

No modifications to mbelib were required, but DSD has been modified to
bypass the sound card.  The GNU Radio block itself was adapted from the
gr-howto-write-a-block sample included with GNU Radio.

Contributions are welcome!

##Examples
**By: Luke Berndt <lukekb@gmail.com>**

I added the examples to help make it a little easier to get started using the gr-dsd block. I have included a GRC file, a python program and example files on how to use the python program. These are all based off of the OP25 Example file from [Baz](http://wiki.spench.net/wiki/OP25).

###GRC File
To use the GRC file, simply load up GNURadio Companion, open the DSD.grc file and connect your SDR. Once you run the file you will see a large FFT that will display all of the spectrum the SDR sees. You can type in the center frequency into the **Frequency** box. You want to pick a center frequency that is close to your target frequency, but not the same. This is because there is some DC interference right at the center frequency. In order to tune in your target frequency, you type in the offset into the **Xlate Offset** box. So if you are trying to tune in 856.8175 Mhz, you could type 856800000 into the **Frequency** box and 17500 into the **Xlating Offset** box. (You may actually need to type -17500, I get confused on this and I think the final frequency display is broken). This will tune you to the correct frequency. 

Unforunately SDRs are not 100% accruate. Click on the **Xlate-1** tab. It will display an FFT of the channel that you are trying to decode. Use **Fine Offset** slider to center the spike of your channel in the middle. You may need to adjust the **Gain** up or down to get it to play correctly. The gain slider adjusts the IF & BB gain used in the HackRF. You could tie it to the RF gain instead if you change the OsmoSDR Source block.

###Python Program
The Python program is the same thing, except without the GUI. You can simply enter the values you used in the GRC program using the command line arguments. If you know how far off your SDR is in the frequency band you are interested, use the **-E** argument. This will let you use the actual frequencies for the channel you are trying to tune in. Again, make sure you tune in a center frequency that is slightly away from your target frequency. You will probably have to adjust the various Gain values to find something that works reliably. I have included some sample Shell Scripts that I use to tune in specific systems.

## Wideband sub-package: `dsd.wideband`

An offline pipeline that ingests a folder of auto-split SDR recordings covering
up to ~10 MHz, detects narrowband digital-voice signals (C4FM/P25, DMR, dPMR,
TETRA), extracts each as a narrowband channel, routes supported protocols to
the existing `dsd.block_ff` decoder, and flags encryption state.

### Runtime dependencies (in addition to gr-dsd / mbelib)
- `numpy`, `scipy`
- optional: `pyyaml` (YAML configs), `matplotlib` (spectrogram PNGs),
  `sigmf` (SigMF captures), `cryptography` (known-key DES decrypt),
  `osmocom-tetra`'s `tetra-rx` on PATH (TETRA decoding).

### Input formats supported
`hackrf_int8`, `rtl_uint8`, `gqrx_fc32` / `cfile`, `SigMF` (`.sigmf-data` +
`.sigmf-meta`), and 1/2-channel `WAV`. Auto-split files are stitched by
lexicographic ordering and file-size gap detection.

### Quick start
```bash
# Create or edit a config file (see python/wideband/example_config.json).
python -m dsd.wideband ingest /path/to/captures --format hackrf_int8
python -m dsd.wideband detect /path/to/captures --sample-rate 10e6
python -m dsd.wideband run  my_config.json
```

See `python/wideband/example_config.json` for a complete template.

### Decoder backends

`decode.dsd_backend` in the config selects how the P25 / DMR family is
decoded:

- `"gr"` (default) — calls `dsd.block_ff` in-process via the gr-dsd GNU Radio
  block. Requires the C++ side of this repo to be built successfully.
- `"subprocess"` — shells out to an external DSD CLI (DSD+, DSDcc, dsd-fme,
  szechyjs/dsd). This is the pragmatic choice on **Windows / radioconda**
  where the gr-dsd C++ block does not build against GNU Radio 3.10. Set:

  ```json
  "decode": {
    "dsd_backend": "subprocess",
    "dsd_binary":  "C:\\\\Tools\\\\dsd-fme\\\\dsd-fme.exe",
    "dsd_flavor":  "dsd_fme",
    "dsd_extra_args": []
  }
  ```

  Recognised flavors: `dsd_fme`, `dsd`, `dsdcc`, `dsdplus`. The runner writes
  the 48 kHz discriminator as a temporary WAV, invokes the binary with
  `-f<mode> -i <in.wav> -w <out.wav>`, reads the 8 kHz output WAV back, and
  parses `NAC`, `algid`, `keyid`, and encryption evidence from its stdout.
