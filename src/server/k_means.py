from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.cluster import KMeans
import numpy as np

class KMeansClassifier(BaseEstimator, ClassifierMixin):

    def __init__(self, n_clusters=3, n_init=10, max_iter=300, random_state=None):
        self.n_clusters = n_clusters
        self.n_init = n_init
        self.max_iter = max_iter
        self.random_state = random_state

    # trinamento
    def fit(self, X, y):
        """ 
        Metodo de treinamento

        Args:
            X (_type_): conjunto de treinamento
            y (_type_): labels para mapear cada cluster

        Returns:
            _type_: _description_
        """
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)

        self.kmeans_ = KMeans(
            n_clusters=self.n_clusters,
            init="k-means++",
            n_init=self.n_init,
            max_iter=self.max_iter,
            random_state=self.random_state,
        ).fit(X)

        self.classes_ = np.unique(y)
        self.cluster_to_class_ = np.empty(self.n_clusters, dtype=y.dtype)
        
        for j in range(self.n_clusters):
            members = y[self.kmeans_.labels_ == j]
            if len(members) == 0:
                self.cluster_to_class_[j] = self.classes_[0]
            else:
                valores, cont = np.unique(members, return_counts=True)
                self.cluster_to_class_[j] = valores[cont.argmax()]
                
        return self

    # predição
    def predict(self, X):
        clusters = self.kmeans_.predict(np.asarray(X, dtype=np.float64))
        return self.cluster_to_class_[clusters]