from typing import List, Union

import numpy as np
from scipy.stats import distributions as dist
from scipy.stats import gaussian_kde as gkde


class DensityProblem(object):
    """
    Sets up Data-Consistent Inverse Problem for parameter identification


    Example Usage
    -------------

    >>> from mud.base import DensityProblem
    >>> from mud.funs import wme
    >>> import numpy as np
    >>> X = np.random.rand(100,1)
    >>> num_obs = 50
    >>> Y = np.repeat(X, num_obs, 1)
    >>> y = np.ones(num_obs)*0.5 + np.random.randn(num_obs)*0.05
    >>> W = wme(Y, y)
    >>> B = DensityProblem(X, W, np.array([[0,1]]))
    >>> np.round(B.mud_point()[0],1)
    0.5

    """

    def __init__(self, X, y, domain=None, weights=None):
        self.X = X
        if y.ndim == 1:
            y = y.reshape(-1, 1)
        self.y = y
        self.domain = domain
        self._r = None
        self._up = None
        self._in = None
        self._pr = None
        self._ob = None
        self._in_dist = None
        self._pr_dist = None
        self._ob_dist = None
        self._up_dist = None

        if self.domain is not None:
            # Assert domain passed in is consitent with dat array
            assert domain.shape[0]==self.X.shape[1]

        # Iniitialize weights
        self.set_set_weights(weights)


    @property
    def _n_features(self):
        return self.y.shape[1]

    @property
    def _n_samples(self):
        return self.y.shape[0]

    def set_weights(self, weights: Union[np.ndarray, List]):
        if weights is None:
            w = np.ones(self.X.shape[0])
        else:
            if isinstance(weights, list):
                weights = np.array(weights)

            # Reshape to 2D
            w = weights.reshape(1,-1) if weights.ndim==1 else weights

            # assert appropriate size
            assert (
                self._n_samples==w.shape[0]
            ), f"`weights` must size {self._n_samples}"

            # Multiply weights column wise for stacked weights
            w = np.prod(w, axis=0)

            # Normalize weight vector
            w = np.divide(w, np.sum(x, axis=0))

        self._weights = w


    def set_observed(self, distribution=dist.norm()):
        """Set distribution for the observed data.

        Parameters
        ----------
        distribution : scipy.stats.rv_continuous, default=scipy.stats.norm()
            scipy.stats continuous distribution like object representing the
            likelihood of observed data. Defaults to a standard normal
            distribution N(0,1).

        """
        self._ob = distribution.pdf(self.y).prod(axis=1)


    def set_initial(self,
            distribution=None):
        """Set initial distribution of model parameter values.

        Parameters
        ----------
        distribution : scipy.stats.rv_continuous, optional
            scipy.stats continuous distribution object from where initial
            parameter samples were drawn from. If non provided, then a uniform
            distribution over domain of density problem is assumed. If no domain
            is specified for density, then a standard normal distribution is
            assumed.

        """
        if distribution is None:  # assume standard normal by default
            if self.domain is not None:  # assume uniform if domain specified
                mn = np.min(self.domain, axis=1)
                mx = np.max(self.domain, axis=1)
                distribution = dist.uniform(loc=mn, scale=mx - mn)
            else:
                distribution = dist.norm()

        initial_dist = distribution
        self._in = initial_dist.pdf(self.X).prod(axis=1)
        self._up = None
        self._pr = None


    def set_predicted(self,
            distribution=None,
            bw_method=None,
            weights=None,
            **kwargs):
        """
        If no distribution is passed, `scipy.stats.gaussian_kde` is used and the
        arguments `bw_method` and `weights` will be passed to it.
        If `weights` is specified, it will be saved as the `self._weights`
        attribute in the class. If omitted, `self._weights` will be used in its place.


        Note: `distribution` should be a frozen distribution if using `scipy`.
        """
        if weights is not None:
            self.set_weights(weights)

        if distribution is None:
            # Reweight kde of predicted by weights from previous iteration if present
            distribution = gkde(self.y.T, bw_method=bw_method, weights=self._weights)
            pred_pdf_values = distribution.pdf(self.y.T).T
        else:
            pred_pdf_values = distribution.pdf(self.y, **kwargs)

        self._pr = pred_pdf_values
        self._up = None


    def fit(self, **kwargs):
        """Update initial distribution using ratio of observed and predicted.

        Applies [] to compute the updated distribution using the ratio of the
        observed to the predicted multiplied by the initial according to the
        data-consistent framework. Note that if initail, predicted, and observed
        distributiosn have not been set before running this method, they will
        be run with default values. To set specific predicted, observed, or
        initial distributions use the `set_` methods.

        Parameteres
        -----------

        Returns
        -----------

        """
        if self._in is None:
            self.set_initial()
            self._pr = None
        if self._pr is None:
            self.set_predicted(**kwargs)
        if self._ob is None:
            self.set_observed()

        # Store ratio of observed/predicted
        # e.g. to comptue E(r) and to pass on to future iterations
        self._r = np.divide(self._ob, self._pr)

        # Multiply by initial to get updated pdf
        up_pdf = np.multiply(self._in * self._weights, self._r)
        self._up = up_pdf


    def mud_point(self):
        """Maximal Updated Density (MUD) Point

        Returns the Maximal Updated Density or MUD point as the parameter sample
        from the initial distribution with the highest update density value.

        Parameters
        ----------

        Returns
        -------
        mud_point : ndarray
            Maximal Updated Density (MUD) point.
        """
        if self._up is None:
            self.fit()
        m = np.argmax(self._up)
        return self.X[m, :]


    def estimate(self):
        """Estimate

        Returns the best estimate for most likely paramter values for the given
        model data using the data-consistent framework.

        Parameters
        ----------

        Returns
        -------
        mud_point : ndarray
            Maximal Updated Density (MUD) point.
        """
        return self.mud_point()


    def exp_r(self):
        """Expectation Value of R

        Returns the expectation value of the R, the ratio of the observed to the
        predicted density values. If the predictability assumption for the data-
        consistent framework is satisfied, then this value should be close to 1
        up to sampling errors.

        Parameters
        ----------

        Returns
        -------
        exp_r : float
            Value of the E(r). Should be close to 1.0.
        """
        if self._up is None:
            self.fit()

        return np.average(self._r, weights=self._weights)


    def plot_param_space(self,
            param_idx=0,
            ax=None,
            x_range=None,
            aff=1000,
            in_opts = {'color':'b', 'linestyle':'--', 'linewidth':4},
            up_opts = {'color':'k', 'linestyle':'-.', 'linewidth':4}):
        """
        Plot probability distributions over parameter space

        """

        if ax is None:
            _, ax = plt.subplots(1, 1)


        # Default x_range to full domain of all parameters
        x_range = x_range if x_range is not None else self.domain
        x_plot = np.linspace(x_range.T[0], x_range.T[1], num=aff)

        if in_opts is not None:
            # Compute initial plot based off of stored initial distribution
            in_plot = self._in_dist.pdf(x_plot)

            # Plot initial distribution over parameter space
            ax.plot(x_plot[:,param_idx], in_plot[:,param_idx], **in_opts)


        if up_opts is not None:
            # Compute r ratio if hasn't been already.
            if self._r is None:
                self.fit()

            # pi_up - kde over params weighted by r times previous weights
            up_plot = gkde(self.X.T, weights=self._r * self._weights)(x_plot.T)
            if self.param_dim==1:
                # Reshape two two-dimensional array if one-dim output
                up_plot = up_plot.reshape(-1,1)

            # Plut updated distribution over parameter space
            ax.plot(x_plot[:,param_idx], up_plot[:,param_idx], **up_opts)


    def plot_obs_space(self,
            obs_idx=0,
            ax=None,
            y_range=None,
            aff=1000,
            pf_in_opts = {'color':'b', 'linestyle':'--', 'linewidth':4},
            pf_up_opts = {'color':'k', 'linestyle':'-.', 'linewidth':4}):
        """
        Plot probability distributions over parameter space
        """

        if ax is None:
            _, ax = plt.subplots(1, 1)

        # Default range is (-1,1) over each observable variable
        if y_range is None:
            y_range = np.repeat([[-1,1]], self.y.shape[1], axis=0)

        # Default x_range to full domain of all parameters
        y_plot = np.linspace(y_range.T[0], y_range.T[1], num=aff)

        if pf_in_opts is not None:
            # Compute PF of initial
            pf_in_plot = self._pr_dist(y_plot.T)
            if self.obs_dim==1:
                # Reshape two two-dimensional array if one-dim output
                pf_in_plot = pf_in_plot.reshape(-1,1)

            # Plot pf of initial
            ax.plot(y_plot[:,obs_idx], pf_in_plot[:,obs_idx], **pf_in_opts)

        if pf_up_opts is not None:
            # Compute r ratio if hasn't been already.
            if self._r is None:
                self.fit()

            # Compute PF of updated
            pf_up_plot = gkde(self.y.T, weights=self._r)(y_plot.T)
            if self.obs_dim==1:
                # Reshape two two-dimensional array if one-dim output
                pf_up_plot = pf_up_plot.reshape(-1,1)

            # Plut pf of updated
            ax.plot(y_plot[:,obs_idx], pf_up_plot[:,obs_idx], **pf_up_opts)



class BayesProblem(object):
    """
    Sets up Bayesian Inverse Problem for parameter identification


    Example Usage
    -------------

    >>> from mud.base import BayesProblem
    >>> import numpy as np
    >>> from scipy.stats import distributions as ds
    >>> X = np.random.rand(100,1)
    >>> num_obs = 50
    >>> Y = np.repeat(X, num_obs, 1)
    >>> y = np.ones(num_obs)*0.5 + np.random.randn(num_obs)*0.05
    >>> B = BayesProblem(X, Y, np.array([[0,1]]))
    >>> B.set_likelihood(ds.norm(loc=y, scale=0.05))
    >>> np.round(B.map_point()[0],1)
    0.5

    """

    def __init__(self, X, y, domain=None):
        self.X = X
        if y.ndim == 1:
            y = y.reshape(-1, 1)
        self.y = y
        self.domain = domain
        self._ps = None
        self._pr = None
        self._ll = None

    @property
    def _n_features(self):
        return self.y.shape[1]

    @property
    def _n_samples(self):
        return self.y.shape[0]

    def set_likelihood(self, distribution, log=False):
        if log:
            self._log = True
            self._ll = distribution.logpdf(self.y).sum(axis=1)
            # below is an equivalent evaluation (demonstrating the expected symmetry)
            # std, mean = distribution.std(), distribution.mean()
            # self._ll = dist.norm(self.y, std).logpdf(mean).sum(axis=1)
        else:
            self._log = False
            self._ll = distribution.pdf(self.y).prod(axis=1)
            # equivalent
            # self._ll = dist.norm(self.y).pdf(distribution.mean())/distribution.std()
            # self._ll = self._ll.prod(axis=1)
        self._ps = None

    def set_prior(self, distribution=None):
        if distribution is None:  # assume standard normal by default
            if self.domain is not None:  # assume uniform if domain specified
                mn = np.min(self.domain, axis=1)
                mx = np.max(self.domain, axis=1)
                distribution = dist.uniform(loc=mn, scale=mx - mn)
            else:
                distribution = dist.norm()
        prior_dist = distribution
        self._pr = prior_dist.pdf(self.X).prod(axis=1)
        self._ps = None

    def fit(self):
        if self._pr is None:
            self.set_prior()
        if self._ll is None:
            self.set_likelihood()

        if self._log:
            ps_pdf = np.add(np.log(self._pr), self._ll)
        else:
            ps_pdf = np.multiply(self._pr, self._ll)

        assert ps_pdf.shape[0] == self.X.shape[0]
        if np.sum(ps_pdf) == 0:
            raise ValueError("Posterior numerically unstable.")
        self._ps = ps_pdf

    def map_point(self):
        if self._ps is None:
            self.fit()
        m = np.argmax(self._ps)
        return self.X[m, :]

    def estimate(self):
        return self.map_point()
