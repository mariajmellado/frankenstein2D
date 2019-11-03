"""This module contains methods for fitting radial brightness profiles to the de-projected visibities.
"""

from __future__ import division, absolute_import, print_function

import numpy as np
import scipy.linalg, scipy.sparse

__all__ = [ "FourierBesselFitter", "FrankFitter"]


class HankelRegressor(object):
    """Solves the Linear Regression problem to compute the posterior
       P(I|q,V,p) ~ G(I-mu, D),
    where I is the intensity to be predicted, q, and V are the baselines and 
    visibility data. 
    
    mu and D are the mean and covariance of the posterior distribution.
    
    If S is provided, it is the covariance matrix of prior
        P(I|p) ~ G(I, S(p)),
    and the Bayesian Linear Regression problem is solved. S is computed from 
    the power spectrum, p, if provided, otherwise the traditional (frequentist)
    Linear Regression is used instead.
    
    The problem is framed in terms of the design matrix, M and information 
    source, j.
    
    H(q) is the matrix that projects the intensity, I, to visibility space and 
    M is defined by
        M = H(q)^T w H(q),
    where w is the weights matrix and
        j = H(q)^T w V.
        
    The mean and covariance of the posterior are then given by
        mu = D j
    and 
        D = [ M + S(p)^-1]^-1
    if the prior is provided, otherwise
        D = M^-1.
    
    Parameters
    -----------
    DHT : DiscreteHankelTransform
        A DHT object with N bins that defines H(p). The DHT is used to compute 
        S(p).
    M : 2D array, size=(N, N)
        The design matrix, see above.
    j : 1D array, size=N
        Information source, see above.
    p : 1D array, size=N, optional
        Power spectrum used to generate the covarience matrix, S(p).
    noise_likelihood : floaat, optional
         An optional parameter needed to compute the full likelihood,
            like_noise = -(1/2) V^T w V - (1/2)*log[det(2*np.pi*N)]
        where V is the visibilities and N is the noise covariance. If not 
        provided, the likelihood can still be computed up to this missing 
        constant.
    """
    def __init__(self, DHT, M, j, p=None, noise_likelihood=0):
            
        self._DHT = DHT
        self._M = M
        self._j = j
        
        self._p = p
        if p is not None:
            Ykm = self._DHT.coefficients()
            p1 = np.where(p > 0, 1./p, 0)
            self._Sinv = np.einsum('ji,j,jk->ik', Ykm, p1, Ykm) 
        else:
            self._Sinv = None
            
        self._like_noise = noise_likelihood
        
        self._fit()
        
    def _fit(self):
        """Compute the mean and variance from M and j.
        
        Parameters
        ----------
        M : 2D array, size=(N, N) 
            The projected precision matrix, 
                M = H(q)^T N^{-1} H(q).
        j : 1D array, size=N
            The projected data vector,
                j = H(q)^T N^-1 V.
        """
        # Compute the inverse Prior covariance, S(p)^-1     
        Sinv = self._Sinv
        if Sinv is None:
            Sinv = 0
            
        Dinv = self._M + Sinv

        try:
            self._Dchol = scipy.linalg.cho_factor(Dinv)
            self._Dsvd  = None
            
            self._mu = scipy.linalg.cho_solve(self._Dchol, self._j)
                
        except np.linalg.LinAlgError as e:
            U, s, V = scipy.linalg.svd(Dinv, full_matrices=False)
            
            s1 = np.where(s > 0, 1./s, 0)
            
            self._Dchol = None
            self._Dsvd  = U, s1, V
                
            self._mu = np.dot(V.T, np.multiply(np.dot(U.T, self._j), s1))
        
        # Reset the covariance matrix - we will compute it when needed.
        self._cov = None
        
    def Dsolve(self, b):
        """Computes np.dot(D, b) by solving D^-1 x = b.
        
        Parameters
        ----------
        b : array, size=(N,...)
            Right hand side to solve for.
            
        Returns 
        -------
        x : array, same shape as b
            Solution to the equation D x = b.
        """
        if self._Dchol is not None:
            return scipy.linalg.cho_solve(self._Dchol, b)
        else:
            U, s1, V = self._Dsvd
            return  np.dot(V.T, np.multiply(np.dot(U.T, b), s1))
        
    def draw(self, N):
        """Compute N draws from the posterior"""
        return np.random.multivariate_normal(self.mean, self.covariance, N)
    
    def log_likelihood(self, I=None):
        """Computes one of two types of likelihood.
        
        If I is provided, this computes
            log[P(I,V|S)],
        otherwise the marginalized likelihood is computed:
            log[P(V|S)].
            
        Parameters
        ----------
        I : array, size=N, optional.
            Intensity, I(r), to compute the likelihood of.
            
        Returns
        -------
        log_P : float,
            log likelihood, log[P(I,V|p)] or log[P(V|p)]
            
        Notes
        -----
        1. The prior probability P(S) is not included. 
        2. The likelihoods take the form:
              log[P(I,V|p)] = (1/2) j^T I - (1/2) I^T D^-1 I 
                 - (1/2)*log[det(2*np.pi*S)]
                 + H_0
           and
              log[P(V|p)] = (1/2) * j^T D j 
                 + (1/2)*log[det(D)/det(S)]
                 + H_0
        where 
            H_0 = (1/2) * V^T w V - (1/2) log[det(2*np.pi*N)]
        is the noise likelihood.
        """
        if I is None:
            like  = 0.5 * np.sum(self._j * self._mu)
  
            if self._Sinv is not None:
                Q = self._Dsolve(self._Sinv)
                like += 0.5 * np.linalg.slogdet(Q)[1]
        else:
            Sinv = self._Sinv
            if Sinv is None:
                Sinv = 0       
                
            Dinv = self._M + Sinv
            
            like = 0.5*np.sum(self._j * I) - 0.5*np.dot(I, np.dot(Dinv, I))
            
            if self._Sinv is not None:
                like += 0.5 * np.linalg.slogdet(2*np.pi*Sinv)[1]
            
        return like + self._like_noise
    
    def predict(self, q, I=None):
        """Predict the visibilities.
        
        Parameters
        ----------
        q : array
            Frequencies to predict the visibilities at.
        I : array, optional
            Intensity points to predict the vibilities of. If not specified, 
            the mean will be used
        """
        if I is None:
            I = self.mean
            
        return self._DHT.transform(I, q)
        
    @property
    def mean(self):
        return self._mu
    @property
    def covariance(self):
        if self._cov is None:
            self._cov = self.Dsolve(np.eye(self.size))
        return self._cov
    
    @property
    def power_spectrum(self):
        """Power spectrum coefficients"""
        return self._p
        
    @property
    def r(self):
        """Radius points"""
        return self._DHT.r
    @property
    def Rmax(self):
        """Maximum Radius"""
        return self._DHT.Rmax
    
    @property
    def q(self):
        """Frequency points"""
        return self._DHT.q
    @property
    def Qmax(self):
        """Maximum frequency"""
        return self._DHT.Qmax
    
    @property
    def size(self):
        """Number of points in reconstruction"""
        return self._DHT.size


class FourierBesselFitter(object):
    """Fourier-Bessel series model for fitting visibilities. 
    
    Parameters
    ----------
    Rmax : float
        Radius of support for the functions to transform, i.e. 
            f(r) = 0 for R >= Rmax
    N : int
        Number of collaction points.
    nu : int default = 0.
        Order of the discrete Hankel transform.
    block_data : bool, default = True
        Large temporary matrices are needed to set up the data, if block_data 
        is True we avoid this, limiting the memory requirement to block_size 
        elements.
    block_size : int, default = 10**7
        Size of the matrices if blocking is used.
    """
    def __init__(self, Rmax, N, nu=0, 
                 block_data=True, block_size = 10**7):
        
        self._DHT = DiscreteHankelTransform(Rmax, N, nu)
                    
        self._blocking = block_data
        self._block_size = block_size
        
    def _build_matrices(self, q, V, weights):
        """Compute the matrices M, and j from the visibility data.
    
        Also computes 
            H0 = 0.5*log[det(w/(2*np.pi))] - 0.5*np.sum(V * w * V)
        """
        # If blocking is used we will build up M and j chunk-by-chunk.
        if self._blocking:
            Nstep = int(self._block_size / self.size + 1)
        else:
            Nstep = len(V)
        
        # Make sure weights are 1D
        w = np.ones_like(V) * weights

        start = 0 ; end = Nstep ; Ndata = len(V)
        M = 0 ; j = 0
        while start < Ndata:
            qs = q[start:end]
            ws = w[start:end]
            Vs = V[start:end]
            
            X = self._DHT.coefficients(qs)
            
            wXT = np.array(X.T*ws, order='C')
    
            M += np.dot(wXT, X)
            j += np.dot(wXT, Vs)
            
            start = end
            end += Nstep
            
        self._M = M
        self._j = j
        
        # Compute likelihood normalization H_0:
        self._H0 = 0.5*np.sum(np.log(w/(2*np.pi)) - V*w*V)
                        
    def fit(self, q, V, weights=1):
        """Fit the visibilties.
        
        Parameters
        ----------
        q : 1D array
            Frequency points of the visibilies.
        V : 1D array
            Visibility amplitudes at q
        weights : 1D array, optional.
            Weights of the visibilities, weight = 1 / sigma^2, where sigma is
            the standard deviation.
            
        Returns
        -------
        sol : HankelRegressor
            Least-squares Fourier-Bessel series fit.
        """
        self._build_matrices(q, V, w)
                        
        self._sol = HankelRegressor(self._DHT, self._M, self._j,
                                    noise_likelihood=self._H0)
                        
        return self._sol
        
    @property
    def r(self):
        """Radius points"""
        return self._DHT.r
    @property
    def Rmax(self):
        """Maximum Radius"""
        return self._DHT.Rmax
    
    @property
    def q(self):
        """Frequency points"""
        return self._DHT.q
    @property
    def Qmax(self):
        """Maximum Frequency"""
        return self._DHT.Qmax
    
    @property
    def size(self):
        """Number of points in reconstruction"""
        return self._DHT.size

    
class FrankFitter(FourierBesselFitter):
    '''Fit a Gaussian process model using the Discrete Hankel Transform of 
    Baddour & Chouinard (2015).
    
    The GP model is based upon Oppermann et al. (2013), which use a maximum 
    aposteriori estimate for the power spectrum as the GP prior for the 
    real-space coefficients.
    
    Parameters
    ----------
    Rmax : float
        Radius of support for the functions to transform, i.e. 
          f(r) = 0 for R >= Rmax
    N : int
        Number of collaction points
    nu : int default = 0.
        Order of the discrete Hankel transform, given by J_nu(r).
    alpha : float >= 1, default = 1.05
        Order parameter of the inverse gamma prior for the power spectrum.
        coefficients.
    p_0 : float >= 0, default = 0.
        Scale parameter of the inverse gamma prior for the power spectrum.
        coefficients.
    smooth : float >= 0, default = 0.1
        Spectral smoothness prior parameter. Zero is no smoothness prior.
    tol : float > 0, default = 1e-3
        Tolerence for convergence of the power spectrum iteration.
    block_data : bool, default = True
        Large temporary matrices are needed to set up the data, if block_data 
        is True we avoid this, limiting the memory requirement to block_size 
        elements.
    block_size : int, default = 10**7
        Size of the matrices if blocking is used.
    
    References
    ----------
        Baddour & Chouinard (2015)
            DOI: https://doi.org/10.1364/JOSAA.32.000611
        Oppermann et al. (2013)
            DOI:  https://doi.org/10.1103/PhysRevE.87.032136
    '''
    def __init__(self, Rmax, N, nu=0,
                 alpha=1.05, p_0=0., w_smooth=0.1,
                 tol=1e-3, max_iter=250,
                 block_data=True, block_size = 10**7):
        
        super(FrankFitter, self).__init__(Rmax, N, nu,
                                             block_data, block_size)
               
        self._p0 = p_0
        self._ai = alpha
        self._smooth = w_smooth
        
        self._tol = tol
        self._max_iter = max_iter
    
    def _build_smoothing_matrix(self):
        log_q = np.log(self.q)
        dc = (log_q[2:] - log_q[:-2]) / 2
        de = np.diff(log_q)
        
        Delta = np.zeros([3, self.size])
        Delta[0,:-2] = 1 / (dc*de[:-1])
        Delta[1,1:-1] = - (1/de[1:] + 1/de[:-1]) / dc
        Delta[2,2:]= 1 / (dc*de[1:])
        
        Delta = scipy.sparse.dia_matrix((Delta, [-1,0,1]),
                                        shape=(self.size, self.size))
        
        dce = np.zeros_like(log_q)
        dce[1:-1] = dc
        dce = scipy.sparse.dia_matrix((dce.reshape(1,-1), 0),
                                      shape=(self.size, self.size))
        
        Tij = Delta.T.dot(dce.dot(Delta))
        
        return Tij*self._smooth
        
    def fit(self, q, V, w=1):
        """Fit the visibilties.
        
        Parameters
        ----------
        q : 1D array
            Frequency points of the visibilies.
        V : 1D array
            Visibility amplitudes at q
        weights : 1D array, optional.
            Weights of the visibilities, weight = 1 / sigma^2, where sigma is
            the standard deviation.
            
        Returns
        -------
        MAP_sol : HankelRegressor
            Reconstructed profile using Maximum a posteriori power spectrum.
        """
        # Project the data to the signal space
        self._build_matrices(q, V, w)
        # Compute the smoothing matrix:
        Tij = self._build_smoothing_matrix()
        
        # Get the forward projection matrix
        Ykm =  self._DHT.coefficients()

        # Weights of each PS component
        rho = 1.0       
        
        # Setup kernel parameters
        pi = np.ones([self.size])
                        
        fit = self.fit_powerspectrum(pi)

        pi[:] = np.max(np.dot(Ykm,fit.mean))**2 / (self._ai + 0.5*rho - 1.0)
        pi[:] *= (self.q/self.q[0])**-2

        fit = HankelRegressor(self._DHT, self._M, self._j, pi)

        # Do one unsmoothed iteration:
        Tr1 = np.dot(Ykm,fit.mean)**2 
        Tr2 = np.einsum('ij,ji->i', Ykm, fit.Dsolve(Ykm.T))
        pi = (self._p0 + 0.5*(Tr1 + Tr2)) / (self._ai-1.0 + 0.5*rho)
                        
        fit = self.fit_powerspectrum(pi)
        
        Tij_pI = scipy.sparse.identity(self.size) + Tij
        sparse_solve = scipy.sparse.linalg.spsolve
                        
        count = 0
        pi_old = 0
        while (np.any(np.abs(pi-pi_old) > self._tol * np.abs(pi)) and
               count <= self._max_iter):
            
            # Project mu to Fourier-space
            #   Tr1 = Trace(mu mu_T . Ykm_T Ykm) = Trace( Ykm mu . (Ykm mu)^T)
            #       = (Ykm mu)**2
            Tr1 = np.dot(Ykm,fit.mean)**2 
            # Project D to Fourier-space:
            #   Drr^-1 = Ykm^T Dqq^-1 Ykm
            #   Drr = Ykm^-1 Dqq Ykm^-T
            #   Dqq = Ykm Dqq Ykm^T
            # Tr2 = Trace(Dqq)
            Tr2 = np.einsum('ij,ji->i', Ykm, fit.Dsolve(Ykm.T))
                        
            beta = (self._p0 + 0.5*(Tr1 + Tr2)) / pi - (self._ai-1.0 + 0.5*rho)
            pi_new = np.exp(sparse_solve(Tij_pI, beta + np.log(pi)))

            pi_old = pi.copy()            
            pi = pi_new
            
            fit = self.fit_powerspectrum(pi)
                        
            count += 1


        # Save the best fit
        self._sol = fit
                        
        # Compute the power-spectrum covariance at the maximum
        self._ps = pi
        self._ps_cov = self._ps_covariance(fit, Tij, rho)
                                
        return self._sol
    
    def _ps_covariance(self, fit, Tij, rho):
        """Covariance of the power-spectrum. 
        
        Parameters
        ----------
        fit : HankelRegressor
            Solution at maximum likelihood
        T : matrix,
            Smoothing matrix
        rho :
            Power spectrum weighting function
            
        Returns
        -------
        ps_cov : 2D array,
            Covariance matrix of the power-spectrum at maximum likelihood.
        
        Notes
        -----
        Only valid at the location of maximum likelihood.
        """
        Ykm =  self._DHT.coefficients()
        
        mq = np.dot(Ykm, fit.mean)
        
        mqq = np.outer(mq, mq)
        Dqq = np.dot(Ykm, fit.Dsolve(Ykm.T))
        
        p = fit.power_spectrum
        tau = np.log(p)
        
        hess =  \
            + np.diag(self._ai-1.0 + 0.5*rho + Tij.dot(tau)) \
            + Tij.todense() \
            - 0.5*np.outer(1/p,1/p)*(2*mqq + Dqq)*Dqq
            
        # Invert the Hessian
        hess_chol = scipy.linalg.cho_factor(hess)
        ps_cov = scipy.linalg.cho_solve(hess_chol, np.eye(self.size))
            
        return ps_cov
                                    
    def draw_powerspectrum(self, Ndraw=1):
        """Draw N sets of power-spectrum parameters.
        
        The draw is takem from the Laplace-approximated (Gaussian) posterior 
        distribution for p,
            P(p) ~ G(p - p_MAP, p_cov)
            
        Parameters
        ----------
        Ndraw : int, default=1
            Number of draws
            
        Returns
        -------
        p : array, size=(N,Ndraw)
            Power spectrum draws.
        """
        log_p = np.random.multivariate_normal(np.log(self._ps), 
                                              self._ps_cov, Ndraw)
        return np.exp(log_p) 
    
    def fit_powerspectrum(self, p):
        """Find the posterior mean and covariance given p.
  
        Parameters
        ----------
        p : array 1D,
            Power spectrum parameters.
            
        Returns
        -------
        sol : HankelRegressor
            Posterior solution object for P(I|V,p)
        """
        return HankelRegressor(self._DHT, self._M, self._j, p, 
                               noise_likelihood=self._H0)
                            
    def log_prior(self, p=None):
        """Compute the log Prior probability, log(P(p)).
        
        log[P(p)] ~ np.sum(p0/pi - alpha*np.log(p0/pi))
            - 0.5*np.log(p) (w_smooth*T) np.log(p)
        
        Parameters
        ----------
        p : array, size=N, optional
            Power spectrum coefficients. If not provided the MAP values are 
            used.
        
        Returns
        -------        
        log[P(p)] : float,
            Log Prior probability.
        
        Notes
        -----
        Computed up to a normalizing constant that depends on alpha, p0.
        """
        if p is None:
            p = self._ps
            
        Tij = self._build_smoothing_matrix()
            
        # Add the power-spectrum prior term
        xi = self._p0/pi
        like = np.sum(xi - self._ai * np.log(xi))
        
        # Extra term due to spectral smoothness
        tau = np.log(pi)
        like -= 0.5* np.dot(tau, Tij.dot(tau))
            
        return like
                            
                
    @property
    def MAP_solution(self):
        """Reconstruction for the maximum a posteriori power spectrum"""
        return self._sol
    
    @property
    def MAP_spectrum(self):
        """Maximum a posteriori power spectrum"""
        return self._ps
    
    @property
    def MAP_spectrum_covariance(self):
        """Covariance matrix of the maximum a posteriori power spectrum"""
        return self._ps_cov
