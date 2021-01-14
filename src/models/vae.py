"""
Abstract VAE class

"""
__date__ = "January 2021"


import torch
import torch.nn as nn



class VAE(nn.Module):

	def __init__(self, encoder, variational_strategy, variational_posterior, \
		prior, decoder, likelihood):
		"""
		Abstract VAE class

		Parameters
		----------
		prior_dist : ...
		likelihood_dist : ...
		variational_dist : ...
		encoder : ...
		decoder : ...
		params : ...
		"""
		super(VAE, self).__init__()
		self.encoder = encoder
		self.variational_strategy = variational_strategy
		self.variational_posterior = variational_posterior
		self.prior = prior
		self.decoder = decoder
		self.likelihood = likelihood
		self.model_type = None
		# # Extra parameters
		# self.params = params
		# Prior distribution parameters
		self._prior_params = None
		# Variational distribution parameters: populated in `forward`
		self._var_dist_params = None


	@property
	def prior_params(self):
		return self._prior_params

	@property
	def var_dist_params(self):
		if self._var_dist_params is None:
			raise NameError("var_dist params not initalised yet!")
		return self._var_dist_params


	def forward(self, x, K=1):
		"""

		Parameters
		----------
		x : ...
		K : ...
		"""
		# Encode data.
		self._qz_x_params = self.encoder(x)
		# Combine evidence and make a variational distribution.
		qz_x = self.qz_x(*self._qz_x_params)
		# Sample from posterior.
		zs = qz_x.rsample(torch.Size([K]))
		# Decode samples to get likelihood distributions.
		px_z = self.px_z(*self.dec(zs))
		# Return the relevant distributions and samples.
		return qz_x, px_z, zs


	def generate(self, N, K):
		self.eval()
		with torch.no_grad():
			pz = self.pz(*self.pz_params)
			latents = pz.rsample(torch.Size([N]))
			px_z = self.px_z(*self.dec(latents))
			data = px_z.sample(torch.Size([K]))
		return data.view(-1, *data.size()[3:])


	def reconstruct(self, data):
		self.eval()
		with torch.no_grad():
			qz_x = self.qz_x(*self.enc(data))
			latents = qz_x.rsample()  # no dim expansion
			px_z = self.px_z(*self.dec(latents))
			recon = get_mean(px_z)
		return recon


	# def analyse(self, data, K):
	# 	self.eval()
	# 	with torch.no_grad():
	# 		qz_x, _, zs = self.forward(data, K=K)
	# 		pz = self.pz(*self.pz_params)
	# 		zss = [pz.sample(torch.Size([K, data.size(0)])).view(-1, pz.batch_shape[-1]),
	# 			   zs.view(-1, zs.size(-1))]
	# 		zsl = [torch.zeros(zs.size(0)).fill_(i) for i, zs in enumerate(zss)]
	# 		kls_df = tensors_to_df(
	# 			[kl_divergence(qz_x, pz).cpu().numpy()],
	# 			head='KL',
	# 			keys=[r'KL$(q(z|x)\,||\,p(z))$'],
	# 			ax_names=['Dimensions', r'KL$(q\,||\,p)$']
	# 		)
	# 	return embed_umap(torch.cat(zss, 0).cpu().numpy()), \
	# 		torch.cat(zsl, 0).cpu().numpy(), \
	# 		kls_df


if __name__ == '__main__':
	pass



###
