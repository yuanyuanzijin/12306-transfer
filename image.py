from PIL import Image

origin_image_dir = "E:\\code\\12306transfer\\origin_imgs\\"
target_image_dir = "E:\\code\\12306transfer\\imgs\\"

for i in range(1, 5):
    img = origin_image_dir + '%d.png' % i
    img_new = target_image_dir + '%d.png' % i
    im = Image.open(img)
    (x, y) = im.size
    if i in [1, 2]:
        x_s = 600
    else:
        x_s = 300
    y_s = int(y * x_s / x)
    out = im.resize((x_s, y_s), Image.ANTIALIAS)
    out.save(img_new)
