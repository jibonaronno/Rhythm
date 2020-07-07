from scipy import fftpack, signal
import matplotlib.pyplot as plt
import numpy as np
#plt.style.use('style/elegant.mplstyle')

class FFTx(object):
    def __init__(self, x):
        self.f_s = 40  # Sampling rate, or number of measurements per second


    def fft(self, x):
        freqs = fftpack.fftfreq(len(x)) * self.f_s
        X = fftpack.fft(x)
        self.fig, self.ax = plt.subplots()
        self.ax.stem(freqs, np.abs(X))
        self.ax.set_xlabel('Frequency in Hertz [Hz]')
        self.ax.set_ylabel('Frequency Domain (Spectrum) Magnitude')
        self.ax.set_xlim(-self.f_s / 2, self.f_s / 2)
        
        #self.ax.set_ylim(-5, 110)
        plt.show()

    def Histogram(self, x):
        plt.hist(x, 10, histtype = 'bar', log=True)
        plt.show()

    def Spectogram(self, x):
        f, t, sxx = signal.spectrogram(x, 10)
        plt.pcolormesh(t, f, sxx)
        plt.ylabel('Frequency [Hz]')
        plt.xlabel('Time [sec]')
        plt.colorbar()
        plt.show()

    def Periodogram(self, x):
        f, Pxx_den = signal.periodogram(x, self.f_s, 'flattop', scaling='spectrum')
        plt.semilogy(f, Pxx_den)
        #plt.ylim([1e-7, 1e2])
        plt.xlabel('frequency [Hz]')
        plt.ylabel('Linear spectrum [V RMS]')
        plt.show()