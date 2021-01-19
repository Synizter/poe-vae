"""
Useful functions and classes.

Contains
--------
* Logger: class
* make_datasets: function
* make_dataloaders: function
* make_vae: function
* make_objective: function
* make_encoder: function
* make_decoder: function
* make_likelihood: function
* check_args: function
* hash_json_str: function
* generate: function
* reconstruct: function
* get_nan_mask: function

"""
__date__ = "January 2021"


import numpy as np
import sys
import torch
from torch.utils.data import DataLoader
from zlib import adler32

from .components import DATASET_MAP, ENCODER_DECODER_MAP, \
		VARIATIONAL_STRATEGY_MAP, VARIATIONAL_POSTERIOR_MAP, PRIOR_MAP, \
		LIKELIHOOD_MAP, OBJECTIVE_MAP
from .components.encoders_decoders import SplitLinearLayer, NetworkList, \
		ModalityEmbeddingCatLayer


DIR_LEN = 8 # for naming the logging directory
IGNORED_KEYS = ['pre_trained', 'epochs'] # for hashing JSON strings



class Logger(object):
	"""
	Logger object for copying stdout to a file.

	Copied from: https://stackoverflow.com/questions/14906764/
	"""

	def __init__(self, filename, mode='a'):
		self.terminal = sys.stdout
		self.log = open(filename, mode)

	def write(self, message):
		self.terminal.write(message)
		self.log.write(message)

	def flush(self):
		pass



def make_datasets(args, train_ratio=0.8):
	"""
	Make train and test Datasets.

	Note: generator should already be seeded -- check this

	Parameters
	----------
	args : argparse.Namespace
	train_ratio : float

	Returns
	-------
	datasets : dict
		Maps the keys 'train' and 'test' to respective Datasets.
	"""
	big_dataset = args.dataset(args.data_fn, args.device)
	train_len = int(round(train_ratio * len(big_dataset)))
	test_len = len(big_dataset) - train_len
	dset_splits = \
			torch.utils.data.random_split(big_dataset, [train_len,test_len]) # NOTE: HERE
	return {'train': dset_splits[0], 'test': dset_splits[1]}


def make_dataloaders(datasets, batch_size):
	"""
	Make train and test DataLoaders.

	Parameters
	----------
	args : argparse.Namespace

	Returns
	-------
	dataloaders : dict
		Maps the keys 'train' and 'test' to respective DataLoaders.
	"""
	dataloaders = {}
	for key in datasets:
		dset = datasets[key]
		dataloaders[key] = DataLoader(dset, batch_size=batch_size, \
				shuffle=(key == 'train'))
	return dataloaders


def make_vae(args):
	"""
	Make a VAE.

	Parameters
	----------
	args : argparse.Namespace

	Returns
	-------
	vae : torch.nn.ModuleDict
	"""
	vae = torch.nn.ModuleDict([ \
			['encoder', make_encoder(args)],
			['variational_strategy', args.variational_strategy()],
			['variational_posterior', args.variational_posterior()],
			['prior', args.prior()],
			['decoder', make_decoder(args)],
			['likelihood', args.likelihood(args.obs_std_dev)],
	])
	return vae.to(args.device)


def make_objective(model, args):
	"""
	Make the objective.

	Parameters
	----------
	model : .vae.VAE
	args : argparse.Namespace

	Returns
	-------
	.components.objectives.VaeObjective (subclasses torch.nn.Module)
	"""
	return args.objective(model).to(args.device)


def make_encoder(args):
	"""
	Make the encoder.

	Each modality gets its own encoder, all with identical architectures.

	Parameters
	----------
	args : argparse.Namespace

	Returns
	-------
	encoder : .components.encoders_decoders.NetworkList (torch.nn.Module)
	"""
	in_dim = args.dataset.modality_dim
	z_dim = args.latent_dim
	output_dims = args.variational_posterior.parameter_dim_func(z_dim)
	net_class = args.encoder
	return _make_net_helper(args, in_dim, output_dims, net_class)


def make_decoder(args):
	"""
	Make the decoder.

	Each modality gets its own decoder, all with identical architectures.

	Parameters
	----------
	args : argparse.Namespace

	Returns
	-------
	decoder : .components.encoders_decoders.NetworkList (torch.nn.Module)
	"""
	in_dim = args.latent_dim
	modality_dim = args.dataset.modality_dim
	output_dims = args.likelihood.parameter_dim_func(modality_dim)
	net_class = args.decoder
	return _make_net_helper(args, in_dim, output_dims, net_class)


def _make_net_helper(args, in_dim, output_dims, net_class):
	"""
	Helper for `make_encoder` and `make_decoder`.

	Parameters
	----------
	args : argparse.Namespace
	in_dim : int
	output_dims : int
	net_class : ...
	"""
	# Collect parameters.
	n_modalities = args.dataset.n_modalities
	# Make layers.
	if args.vectorized:
		# First make the modality embedding.
		embed_layer = ModalityEmbeddingCatLayer(n_modalities, args.m_dim)
		# Then make the rest of the layers.
		dims = [in_dim+args.m_dim] + \
						[args.hidden_layer_dim] * args.num_hidden_layers
		encoder = net_class(dims)
		last_layer = SplitLinearLayer(args.hidden_layer_dim, output_dims) # MAKE VECTORIZED!
		return torch.nn.Sequential(embed_layer, encoder, last_layer)
	else:
		# Make everything up to the last layer.
		dims = [in_dim] + [args.hidden_layer_dim]*args.num_hidden_layers
		encoders = [net_class(dims) for _ in range(n_modalities)]
		for i in range(n_modalities):
			last_layer = SplitLinearLayer(args.hidden_layer_dim, output_dims)
			encoders[i] = torch.nn.Sequential(encoders[i], last_layer)
		return NetworkList(torch.nn.ModuleList(encoders))


def make_likelihood(args):
	"""
	Make the VAE likelihood.

	Parameters
	----------
	args : argparse.Namespace
	"""
	raise NotImplementedError


def check_args(args):
	"""
	Check the arguments, replacing names with objects.

	TO DO: check compatibility!

	Parameters
	----------
	args : argparse.Namespace
	"""
	# First, map VAE component names to classes.
	args.dataset = DATASET_MAP[args.dataset]
	args.encoder = ENCODER_DECODER_MAP[args.encoder]
	args.variational_strategy = \
				VARIATIONAL_STRATEGY_MAP[args.variational_strategy]
	args.variational_posterior = \
				VARIATIONAL_POSTERIOR_MAP[args.variational_posterior]
	args.prior = PRIOR_MAP[args.prior]
	args.decoder = ENCODER_DECODER_MAP[args.decoder]
	args.likelihood = LIKELIHOOD_MAP[args.likelihood]
	args.objective = OBJECTIVE_MAP[args.objective]
	# Next, make sure the components are compatible.
	args.vectorized = args.dataset.vectorized_modalities
	# TO DO: finish this!
	pass


def hash_json_str(json_str):
	"""Hash the JSON string to get a logging directory name."""
	json_str = [line for line in json_str.split('\n') if \
			not any(ignore_str in line for ignore_str in IGNORED_KEYS)]
	json_str = '\n'.join(json_str)
	exp_dir = str(adler32(str.encode(json_str))).zfill(DIR_LEN)[-DIR_LEN:]
	return exp_dir


def generate(vae, n_samples=9, decoder_noise=False):
	"""
	Generate data with a VAE.

	Parameters
	----------
	vae :
	n_samples : int
	decoder_noise : bool

	Returns
	-------
	generated : numpy.ndarray
	"""
	vae.eval()
	with torch.no_grad():
		z_samples = vae.prior.rsample(n_samples=n_samples) # [1,n,z]
		print("z_samples", z_samples.shape)
		like_params = vae.decoder(z_samples) # [m][param_num][1,n,z]
		if decoder_noise:
			assert hasattr(vae.likelihood, 'rsample')
			generated = vae.likelihood.rsample(like_params, n_samples=n_samples)
		else:
			assert hasattr(vae.likelihood, 'mean')
			generated = vae.likelihood.mean(like_params, n_samples=n_samples)
	return np.array([g.detach().cpu().numpy() for g in generated])


def reconstruct(vae, data, decoder_noise=False):
	"""
	Reconstruct data with a VAE.

	Parameters
	----------

	Returns
	-------

	"""
	vae.eval()
	with torch.no_grad():
		nan_mask = get_nan_mask(data)
		for i in range(len(data)):
			data[i][nan_mask[i]] = 0.0
		var_dist_params = vae.encoder(data)
		var_post_params = vae.variational_strategy(*var_dist_params, \
				nan_mask=nan_mask)
		z_samples, _ = vae.variational_posterior(*var_post_params, \
				transpose=False)
		print("z_samples", z_samples.shape)
		like_params = vae.decoder(z_samples)
		if decoder_noise:
			assert hasattr(vae.likelihood, 'rsample')
			generated = vae.likelihood.rsample(like_params, n_samples=1)
		else:
			assert hasattr(vae.likelihood, 'mean')
			generated = vae.likelihood.mean(like_params, n_samples=1)
	return np.array([g.detach().cpu().numpy() for g in generated])


def get_nan_mask(xs):
	"""Return a mask indicating which minibatch items are NaNs."""
	if type(xs) == type([]):
		return [torch.isnan(x[:,0]) for x in xs]
	else:
		raise NotImplementedError


if __name__ == '__main__':
	pass



###
