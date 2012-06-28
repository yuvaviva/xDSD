/* -*- c++ -*- */
/*
 * Copyright 2004 Free Software Foundation, Inc.
 *
 * This file is part of GNU Radio
 *
 * GNU Radio is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3, or (at your option)
 * any later version.
 *
 * GNU Radio is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with GNU Radio; see the file COPYING.  If not, write to
 * the Free Software Foundation, Inc., 51 Franklin Street,
 * Boston, MA 02110-1301, USA.
 */
#ifndef INCLUDED_DSD_BLOCK_FF_H
#define INCLUDED_DSD_BLOCK_FF_H

#include <dsd_api.h>
#include <gr_sync_decimator.h>

extern "C"
{
  #include <dsd.h>
}

typedef struct
{
  dsd_opts opts;
  dsd_state state;
} dsd_params;

class dsd_block_ff;

/*
 * We use boost::shared_ptr's instead of raw pointers for all access
 * to gr_blocks (and many other data structures).  The shared_ptr gets
 * us transparent reference counting, which greatly simplifies storage
 * management issues.  This is especially helpful in our hybrid
 * C++ / Python system.
 *
 * See http://www.boost.org/libs/smart_ptr/smart_ptr.htm
 *
 * As a convention, the _sptr suffix indicates a boost::shared_ptr
 */
typedef boost::shared_ptr<dsd_block_ff> dsd_block_ff_sptr;

/*!
 * \brief Return a shared_ptr to a new instance of dsd_block_ff.
 *
 * To avoid accidental use of raw pointers, dsd_block_ff's
 * constructor is private.  dsd_make_block_ff is the public
 * interface for creating new instances.
 */
DSD_API dsd_block_ff_sptr dsd_make_block_ff ();

/*!
 * \brief pass discriminator output through Digital Speech Decoder
 * \ingroup block
 */
class DSD_API dsd_block_ff : public gr_sync_decimator
{
private:
  // The friend declaration allows dsd_make_block_ff to
  // access the private constructor.

  friend DSD_API dsd_block_ff_sptr dsd_make_block_ff ();

  dsd_params params;

  /*!
   * \brief pass discriminator output thread Digital Speech Decoder
   */
  dsd_block_ff ();  	// private constructor

 public:
  ~dsd_block_ff ();	// public destructor

  // Where all the action really happens

  int work (int noutput_items,
	    gr_vector_const_void_star &input_items,
	    gr_vector_void_star &output_items);
};

#endif /* INCLUDED_DSD_BLOCK_FF_H */