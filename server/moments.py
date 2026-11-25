import numpy 
import cv2 as opencv 

# Momentos da imagem
def moments(p: int, q: int, img):
    
    h, w = img.shape[:2]
    mpq = 0
    
    for x in range(0, h):
        for y in range(0, w):
            mpq += numpy.pow(x, p) * numpy.pow(y, q) * img[x, y]
         
    return mpq 

# Momentos centrais
def centralized_moments(p, q, img):
    
    # centroid da imagem 
    c_x = moments(1, 0, img) / moments(0, 0, img)
    c_y = moments(0, 1, img) / moments(0, 0, img)
    
    h, w = img.shape[:2]
    
    npq = 0
    
    for x in range(0, h):
        for y in range(0, w):
            npq += numpy.pow(x - c_x, p) * numpy.pow(y - c_y, q) * img[x, y]
            
    return npq
            
# Momentos invariantes a escala
def scale_invariant_moments(p, q, img):
    vpq = centralized_moments(p, q, img)
    v00 = centralized_moments(0, 0, img)
    
    y = ((p + q) / 2) + 1 # com (p + q) >= 2
    
    return (vpq) / numpy.pow(v00, y) 

# This vector contains translation, scale, and rotation invariant and orientation related moments. 
def rot_invariant_moments(img):
    
    # momentos base 
    m00 = moments(0, 0, img)
    m10 = moments(1, 0, img)
    m01 = moments(0, 1, img)
    m20 = moments(2, 0, img)
    m11 = moments(1, 1, img)
    m02 = moments(0, 2, img)
    m30 = moments(3, 0, img)
    m21 = moments(2, 1, img)
    m12 = moments(1, 2, img)
    m03 = moments(0, 3, img)
 
    # momentos centrais
    mu20 = centralized_moments(2, 0, img)
    mu11 = centralized_moments(1, 1, img)
    mu02 = centralized_moments(0, 2, img)
    mu30 = centralized_moments(3, 0, img)
    mu21 = centralized_moments(2, 1, img)
    mu12 = centralized_moments(1, 2, img)
    mu03 = centralized_moments(0, 3, img)
    
    n20 = scale_invariant_moments(2, 0, img)
    n02 = scale_invariant_moments(0, 2, img)
    n11 = scale_invariant_moments(1, 1, img)
    n30 = scale_invariant_moments(3, 0, img)
    n12 = scale_invariant_moments(1, 2, img)
    n21 = scale_invariant_moments(2, 1, img)
    n03 = scale_invariant_moments(0, 3, img)
    
    I1 = n20 + n02 
    I2 = numpy.pow(n20 - n02, 2) + numpy.pow(2 * n11, 2)
    I3 = numpy.pow(n30 - (3 * n12), 2) + numpy.pow((3 * n21) - n03, 2)
    I4 = numpy.pow(n30 + n12, 2) + numpy.pow(n21 + n03, 2)
    I5 = (n30 - (3 * n12)) * (n30 + n12) * (numpy.pow(n30 + n12, 2) - (3 * numpy.pow(n21 + n03, 2))) + (3 * (n21) - n03) * (n21 + n03) * (3 * numpy.pow(n30 + n12, 2) - numpy.pow(n21 + n03, 2))
    I6 = (n20 - n02) * (numpy.pow(n30 + n12, 2) - numpy.pow(n21 + n03, 2)) + ((4 * n11) * (n30 + n12) * (n21 + n03))
    I7 = ((3 * n21) - n03) * (n30 + n12) * (numpy.pow(n30 + n12, 2) - (3 * numpy.pow(n21 + n03, 2))) - (n30 - (3 * n12)) * (n21 + n03) * ((3 * numpy.pow(n30 + n12, 2)) - numpy.pow(n21 + n03, 2))
    I8 = (n11 * (numpy.pow(n30 + n12, 2) - numpy.pow(n03 + n21, 2))) - (n20 - n02) * (n30 + n12) * (n03 + n21)
        
    return {
        "m00" : m00,
        "m10" : m10,
        "m01" : m01,
        "m20" : m20,
        "m11" : m11,
        "m02" : m02,
        "m30" : m30,
        "m21" : m21,
        "m12" : m12,
        "m03" : m03,
        "mu20" : mu20,
        "mu11" : mu11,
        "mu02" : mu02,
        "mu30" : mu30,
        "mu21" : mu21,
        "mu12" : mu12,
        "mu03" : mu03,
        "nu20" : n20,
        "nu02" : n02,
        "nu11" : n11,
        "nu30" : n30,
        "nu12" : n12,
        "nu21" : n21,
        "nu03" : n03,
        "I1": I1,
        "I2": I2,
        "I3": I3,
        "I4": I4,
        "I5": I5,
        "I6": I6, 
        "I7": I7,
        "I8": I8
    }