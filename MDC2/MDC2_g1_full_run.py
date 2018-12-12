from __future__ import division

import numpy as np
import glob, os, json
import matplotlib.pyplot as plt
import scipy.linalg as sl

import libstempo as libs
import libstempo.plot as libsplt

import enterprise
from enterprise.pulsar import Pulsar
from enterprise.signals import parameter
from enterprise.signals import white_signals
from enterprise.signals import utils
from enterprise.signals import gp_signals
from enterprise.signals import signal_base

import corner
from PTMCMCSampler.PTMCMCSampler import PTSampler as ptmcmc

#NEED TO CHANGE FILE ON DIFFERENT RUNS (ie full_run_1 -> full_run_2)
runname = '/full_run_2'
dataset = '/dataset_1b'

topdir = os.getcwd()
#Where the original data is
origdatadir = topdir + '/mdc2/group1' + dataset
#Where the json noise file is
noisefile = topdir + '/mdc2/group1/challenge1_psr_noise.json'
#Where the dataset files are located
datadir = topdir + dataset
#Where the everything should be saved to (chains, cornerplts, histograms, etc.)
outdir = datadir + runname
#Where we save figures n stuff
figdir = datadir + '/Cornerplts/'
#The new json file we made
updatednoisefile = noisedir + 'fit_psr_noise.json'

if os.path.exists(datadir) == False:
    os.mkdir(datadir)
if os.path.exists(outdir) == False:
    os.mkdir(outdir)

parfiles = sorted(glob.glob(origdatadir + '/*.par'))
timfiles = sorted(glob.glob(origdatadir + '/*.tim'))

#Loading par and tim files into enterprise Pulsar class
psrs = []
for p, t in zip(parfiles, timfiles):
    psr = Pulsar(p, t)
    psrs.append(psr)

'''
#Get true noise values for pulsar to plot in corner plot (truth values)
with open(noisefile, 'r') as nf:
	noise_dict = json.load(nf)
	nf.close()
#Unpacking dictionaries in json file to get at noise values
params = {}
for psr in psrs:
	params.update(noise_dict[psr.name])
'''

# find the maximum time span to set GW frequency sampling
tmin = [p.toas.min() for p in psrs]
tmax = [p.toas.max() for p in psrs]
Tspan = np.max(tmax) - np.min(tmin)

##### parameters and priors #####

# white noise parameters
efac = parameter.Uniform(0.5,3.0)
log10_equad = parameter.Uniform(-8.5,5)

# red noise parameters
red_noise_log10_A = parameter.Uniform(-20,-11)
red_noise_gamma = parameter.Uniform(0,7)

# GW parameters (initialize with names here to use parameters in common across pulsars)
log10_A_gw = parameter.LinearExp(-18,-12)('zlog10_A_gw')
gamma_gw = parameter.Constant(13/3)('zgamma_gw')

##### Set up signals #####

# timing model
tm = gp_signals.TimingModel()

# white noise
ef = white_signals.MeasurementNoise(efac=efac)
eq = white_signals.EquadNoise(log10_equad = log10_equad)

# red noise (powerlaw with 30 frequencies)
pl = utils.powerlaw(log10_A=red_noise_log10_A, gamma=red_noise_gamma)
rn = gp_signals.FourierBasisGP(spectrum=pl, components=30, Tspan=Tspan)


cpl = utils.powerlaw(log10_A=log10_A_gw, gamma=gamma_gw)
# Hellings and Downs ORF
orf = utils.hd_orf()

#Common red noise process with no correlations
#crn = gp_signals.FourierBasisGP(spectrum = cpl, components=30, Tspan=Tspan, name = 'gw')

# gwb with Hellings and Downs correlations
gwb = gp_signals.FourierBasisCommonGP(pl, orf, components=30, name='gw', Tspan=Tspan)

# full model is sum of components
model = ef + eq + rn + tm + gwb

# initialize PTA
pta = signal_base.PTA([model(psr) for psr in psrs])

#make dictionary of pulsar parameters from these runs
param_dict = {}
for psr in pta.pulsars:
    param_dict[psr] = {}
    for param, idx in zip(pta.param_names,range(len(pta.param_names))):
        if param.startswith(psr):
            param_dict[psr][param] = idx
#Save to json file
with open(outdir + '/Search_params.json','w') as paramfile:
    json.dump(param_dict,paramfile,sort_keys = True,indent = 4)
    paramfile.close()

#Pick random initial sampling
xs = {par.name: par.sample() for par in pta.params}

# dimension of parameter space
ndim = len(xs)

# initial jump covariance matrix
cov = np.diag(np.ones(ndim) * 0.01**2)

# set up jump groups by red noise groups
ndim = len(xs)
groups  = [range(0, ndim)]
groups.extend(map(list, zip(range(0,ndim,2), range(1,ndim,2))))
groups.extend([[36]])

# intialize sampler
sampler = ptmcmc(ndim, pta.get_lnlikelihood, pta.get_lnprior, cov, groups=groups, outDir = outdir)

# sampler for N steps
N = 100000
x0 = np.hstack(p.sample() for p in pta.params)
sampler.sample(x0, N, SCAMweight=30, AMweight=15, DEweight=50)