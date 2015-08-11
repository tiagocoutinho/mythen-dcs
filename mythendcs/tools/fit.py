import numpy as np
from scipy.special import wofz
import math

class Func(object):
    Gauss = gauss
    GaussC = gauss_c
    Lorentz = lorentz_c
    pVoigt = p_voigt
    Pearson7 = pearson7


def gauss(x, a, x0, sigma):
    """
    :param x:
    :param a:
    :param x0:
    :param sigma:
    :return:
    """
    func = a * np.exp((-(x-x0)**2)/(2*sigma**2))
    return func

def gauss_c(x, a, x0, sigma, c):
    """
    :param x:
    :param a:
    :param x0:
    :param sigma:
    :param c:
    :return:
    """
    func = gauss(x, a, x0, sigma) + c
    return func

def lorentz_c(x, a, x0, sigma, c):
    """
    :param x:
    :param a:
    :param x0:
    :param sigma:
    :param c:
    :return:
    """
    func = a * ((sigma**2)/((x - x0)**2 + sigma**2)) + c
    return func

def p_voigt(x, g, x0, sigma, c):
    """
    :param x:
    :param g:
    :param x0:
    :param sigma:
    :param c:
    :return:
    """
    z = ((x-x0)+g*1j)/(sigma*math.sqrt(2.0))
    func = np.real(wofz(z))/(sigma*math.sqrt(2*math.pi))
    return func

def pearson7(x, x0, sigma, shape, amp,c):
    """
    :param x:
    :param x0:
    :param sigma:
    :param shape:
    :param amp:
    :param c:
    :return:
    """
    func = amp*(1.0+(2.0**(1.0/shape)-1.0)*(2.0*(x-x0)/sigma)**2)**(-shape) + c
    return func
