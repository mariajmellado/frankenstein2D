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
"""Run Frankenstein to fit a source's 1D radial brightness profile.
   A default parameter file is used that specifies all options to run the fit
   and output results. Alternatively a custom parameter file can be provided.
"""

import os
import sys
import time
import json
import numpy as np

parameter_file = "default_parameters.json"


def helper():
    with open('parameter_descriptions.json') as f:
        param_descrip = json.load(f)

    print("""
     Fit a 1D radial brightness profile with Frankenstein (frank) from the
     terminal with `python -m frank.fit`. A .json parameter file is required;
     the default is default_parameters.json and is of the form:\n\n""",
     json.dumps(param_descrip, indent=4))


def parse_parameters(parameter_file):
    import argparse

    parser = argparse.ArgumentParser("Run a Frank fit, by default using"
                                     " parameters in default_parameters.json")
    parser.add_argument("-p", "--parameters", default=parameter_file, type=str,
                        help="Parameter file (.json)")
    parser.add_argument("-uv", "--uvtable_filename", default=None, type=str,
                        help="Data file to be fit (.txt)")

    args = parser.parse_args()
    model = json.load(open(args.parameters, 'r'))

    if args.uvtable_filename:
        model['input_output']['uvtable_filename'] = args.uvtable_filename

    if not model['input_output']['uvtable_filename']:
        sys.exit("    Error: uvtable_filename isn't specified in the parameter"
                 " file. Update it there or run frank with"
                 " python -m frank.fit -uv <uvtable_filename>")

    if not model['input_output']['load_dir']:
        model['input_output']['load_dir'] = os.getcwd()

    if not model['input_output']['save_dir']:
        model['input_output']['save_dir'] = model['input_output']['load_dir']

    print('\nRunning frank on', model['input_output']['uvtable_filename'])

    print('  Saving parameters to be used in fit to `used_params.json`')
    with open('used_params.json', 'w') as f:
        json.dump(model, f, indent=4)

    return model


def load_uvdata(data_file):
    print('  Loading UVTable')

    u, v, vis, weights = np.genfromtxt(data_file).T

    return u, v, vis, weights


def determine_geometry(model, u, v, vis, weights):
    print('  Determining disc geometry')

    if not model['geometry']['fit_geometry']:
        from frank.geometry import FixedGeometry
        geom = FixedGeometry(0., 0., 0., 0.)

    else:
        if model['geometry']['known_geometry']:
            from frank.geometry import FixedGeometry

            geom = FixedGeometry(model['geometry']['inc'],
                                 model['geometry']['pa'],
                                 model['geometry']['dra'],
                                 model['geometry']['ddec']
                                 )

        else:
            from frank.geometry import FitGeometryGaussian

            if model['geometry']['fit_phase_offset']:
                geom = FitGeometryGaussian()

            else:
                geom = FitGeometryGaussian(phase_centre=(model['geometry']['dra'],
                                           model['geometry']['ddec']))

            t1 = time.time()
            geom.fit(u, v, vis, weights)
            print('    Time taken to fit geometry %.2f sec'%(time.time() - t1))

    print('    Using: inc %.2f deg,\n           PA %.2f deg,\n'
          '           dRA %.2e arcsec,\n           dDec %.2e arcsec'
          %(geom.inc, geom.PA, geom.dRA, geom.dDec))

    return geom


def perform_fit(model, u, v, vis, weights, geom):
    print('  Fitting for brightness profile')

    from frank.radial_fitters import FrankFitter

    FF = FrankFitter(Rmax=model['hyperpriors']['rout'],
                     N=model['hyperpriors']['n'],
                     geometry=geom,
                     alpha=model['hyperpriors']['alpha'],
                     weights_smooth=model['hyperpriors']['wsmooth']
                     )

    t1 = time.time()
    sol = FF.fit(u, v, vis, weights)
    print('    Time taken to fit profile (with %.0e visibilities and %s'
          ' collocation points) %.2f sec'%(len(vis), model['hyperpriors']['n'],
          time.time() - t1))

    return sol


def output_results(model, u, v, vis, weights, sol, diag_fig=True):
    print(dir(sol))
    if model['input_output']['save_profile_fit']:
        np.savetxt(savedir + 'fit.txt',
                   np.array([sol.r, sol.mean, np.diag(sol.covariance)**.5]).T,
                   header='r [arcsec]\tI [Jy/sr]\tI_err [Jy/sr]')

    if model['input_output']['save_vis_fit']:
        np.savetxt(savedir + 'fit_vis.txt',
                   np.array([ki / (2 * np.pi), GPHF.HankelTransform(ki)]).T,
                   header='Baseline [lambda]\tRe(V) [Jy]')

    if model['input_output']['save_uvtables']:
        np.save(savedir + disc + '_frank_fit.dat',
                np.stack([u_proj, v_proj, re_proj, im_proj, weights_orig], axis=-1))
        np.save(savedir + disc + '_frank_residuals.dat',
                np.stack([u_proj, v_proj, re_proj, im_proj, weights_orig], axis=-1))

    if model['input_output']['make_plots']:
        frank.plot(model, u, v, vis, weights, sol)
        if model['input_output']['save_plots']:
            frank.save_plot(fn)


def main():
    model = parse_parameters(parameter_file)

    u, v, vis, weights = load_uvdata(model['input_output']['uvtable_filename'])

    geom = determine_geometry(model, u, v, vis, weights)

    perform_fit(model, u, v, vis, weights, geom)

    #output_results(model, u, v, vis, weights, sol)

    print("IT'S ALIVE!!\n")

if __name__ == "__main__":
    main()
