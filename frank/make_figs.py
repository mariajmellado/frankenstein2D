# Frankenstein: 1D disc brightness profile reconstruction from Fourier data
# using non-parametric Gaussian Processes
#
# Copyright (C) 2019-2020  R. Booth, J. Jennings, M. Tazzari
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>
#
"""This module generates figures for a Frankenstein fit and/or its diagnostics.
"""
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from frank import plot, useful_funcs


def make_fit_fig(u, v, vis, weights, sol, save_dir, uvtable_filename, bin_widths, dist):
    prefix = save_dir + '/' + os.path.splitext(uvtable_filename)[0]

    gs = GridSpec(3, 2, hspace=0)
    fig = plt.figure(figsize=(20,16))

    ax0 = fig.add_subplot(gs[0])
    ax1 = fig.add_subplot(gs[2])
    ax3 = fig.add_subplot(gs[1])
    ax4 = fig.add_subplot(gs[3])
    ax5 = fig.add_subplot(gs[5])

    plot.plot_brightness_profile(sol.r, sol.mean, ax0)
    plot.plot_brightness_profile(sol.r, sol.mean, ax1, yscale='log')

    u_deproj, v_deproj, vis_deproj = sol.geometry.apply_correction(u, v, vis)
    baselines = (u_deproj**2 + v_deproj**2)**.5
    grid = np.logspace(np.log10(min(baselines.min(), sol.q[0])),
                       np.log10(max(baselines.max(), sol.q[-1])),
                       10**4)

    for i in bin_widths:
        print('this bin width',i)
        binned_vis = useful_funcs.BinUVData(baselines, vis_deproj, weights, i)

        plot.plot_binned_vis(binned_vis.uv, binned_vis.V.real,
            binned_vis.error.real, ax3, zoom=True)

        plot.plot_vis_resid(binned_vis.uv, binned_vis.V.real,
            sol.predict_deprojected(binned_vis.uv).real, ax5)

    plot.plot_vis_fit(grid, sol.predict_deprojected(grid).real, ax3)

    plot.plot_vis_fit(grid, sol.predict_deprojected(grid).real, ax4)

    plt.setp(ax0.get_xticklabels(), visible=False)
    plt.setp(ax3.get_xticklabels(), visible=False)
    plt.setp(ax4.get_xticklabels(), visible=False)

    plt.savefig(prefix + '_frank_fit.png')

    return fig

def make_diag_fig(u, v, vis, weights, sol, save_dir, uvtable_filename, bin_widths, dist):
    prefix = save_dir + '/' + os.path.splitext(uvtable_filename)[0]

    gs = GridSpec(2, 2, hspace=0)
    fig = plt.figure(figsize=(20,16))

    for i in bin_widths:
        binned_vis = useful_funcs.BinUVData(baselines, vis_deproj, weights, i)
        plot.plot_binned_vis(binned_vis.uv, binned_vis.V.imag, binned_vis.error.imag, ax5, plot_CIs=False)

    plt.savefig(prefix + '_frank_diag.png')

    return fig
