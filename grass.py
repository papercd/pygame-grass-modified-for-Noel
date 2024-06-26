'''
Version 1.0

An efficient pure Python/Pygame grass module written by DaFluffyPotato. Feel free to use however you'd like.

Please see grass_demo.py for an example of how to use GrassManager.

Important functions and objects:

-> grass.GrassManager(grass_path, tile_size=15, shade_amount=100, stiffness=360, max_unique=10, place_range=[1, 1], padding=13)
Initialize a grass manager object.

-> grass.GrassManager.enable_ground_shadows(shadow_strength=40, shadow_radius=2, shadow_color=(0, 0, 1), shadow_shift=(0, 0))
Enables shadows for individual blades (or disables if shadow_strength is set to 0). shadow_radius determines the radius of the
shadow circle, shadow_color determines the base color of the shadow, and shadow_shift is the offset of the shadow relative to
the base of the blade.

-> grass.GrassManager.place_tile(location, density, grass_options)
Adds new grass. location specifies which "tile" the grass should be placed at, so the pixel-position of the tile will depend
on the GrassManager's tile size. density specifies the number of blades the tile should have and grass_options is a list of blade
image IDs that can be used to form the grass tile. The blade image IDs are the alphabetical index of the image in the asset folder
provided for the blades. Please note that you can specify the same ID multiple times in the grass options to make it more likely
to appear.

-> grass.GrassManager.apply_force(location, radius, dropoff)
Applies a physical force to the grass at the given location. The radius is the range at which the grass should be fully bent over at.
The dropoff is the distance past the end of the "radius" that it should take for the force to be eased into nothing.

-> grass.GrassManager.update_render(surf, dt, offset=(0, 0), rot_function=None)
Renders the grass onto a surface and applies updates. surf is the surface rendered onto, dt is the amount of seconds passed since the
last update, offset is the camera's offset, and the rot_function is for custom rotational modifiers. The rot_function passed as an
argument should take an X and Y value while returning a rotation value. Take a look at grass_demo.py to how you can create a wind
effect with this.

Notes about configuration of the GrassManager:

<grass_path>
The only required argument. It points to a folder with all of the blade images. The names of the images don't matter. When creating
tiles, you provide a list of IDs, which are the indexes of the blade images that can be used. The indexes are based on alphabetical
order, so if be careful with numbers like img_2.png and img_10.png because img_10.png will come first. It's recommended that you do
img_02.png and img_10.png if you need double digits.

<tile_size>
This is used to define the "tile size" for the grass. If your game is tile based, your actual tile size should be some multiple of the
number given here. This affects a couple things. First, it defines the smallest section of grass that can be individually affected by
efficient rotation modifications (such as wind). Second, it affects performance. If the size is too large, an unnecessary amount of
calculations will be made for applied forces. If the size is too small, there will be too many images render, which will also reduce
performance. It's good to play around with this number for proper optimization.

<shade_amount>
The shade amount determines the maximum amount of transparency that can be applied to a blade as it tilts away from its base angle.
This should be a value from 0 to 255.

<stiffness>
This determines how fast the blades of grass bounce back into place after being rotated by an applied force.

<max_unique>
This determines the maximum amount of variants that can be used for a specific tile configuration (a configuration is the combination
of the amount of blades of grass and the possible set of blade images that can be used for a tile). If the number is too high, the
application will use a large amount of RAM to store all of the cached tile images. If the number is too low, you'll start to see
consistent patterns appear in the layout of your grass tiles.

<place_range>
This determines the vertical range that the base of the blades can be placed at. The range should be any range in the range of 0 to 1.
Use [1, 1] when you want the base of the blades to be placed at the bottom of the tile (useful for platformers) or [0, 1] if you want
the blades to be placed anywhere in the tile (useful for top-down games).

<padding>
This is the amount of spacial padding the tile images have to fit the blades spilling outside the bounds of the tile. This should
probably be set to the height of your tallest blade of grass.
'''

import os
import random
import math
from copy import deepcopy

import pygame

BURN_CHECK_OFFSETS = [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]

def normalize(val, amt, target):
    if val > target + amt:
        val -= amt
    elif val < target - amt:
        val += amt
    else:
        val = target
    return val

# the main object that manages the grass system
class GrassManager:
    def __init__(self, grass_path, tile_size=15, shade_amount=100, stiffness=360, max_unique=10, place_range=[1, 1], padding=13):
        # asset manager
        self.ga = GrassAssets(grass_path, self)

        # caching variables
        self.grass_id = 0
        self.grass_cache = {}
        self.shadow_cache = {}
        self.formats = {}

        # tile data
        self.grass_tiles = {}

        # config
        self.tile_size = tile_size
        self.shade_amount = shade_amount
        self.stiffness = stiffness
        self.max_unique = max_unique
        self.vertical_place_range = place_range
        self.ground_shadow = [0, (0, 0, 0), 100, (0, 0)]
        self.padding = padding

    # enables circular shadows that appear below each blade of grass
    def enable_ground_shadows(self, shadow_strength=40, shadow_radius=2, shadow_color=(0, 0, 1), shadow_shift=(0, 0)):
        # don't interfere with colorkey
        if shadow_color == (0, 0, 0):
            shadow_color = (0, 0, 1)

        self.ground_shadow = [shadow_radius, shadow_color, shadow_strength, shadow_shift]

    # either creates a new grass tile layout or returns an existing one if the cap has been hit
    def get_format(self, format_id, data, tile_id):
        if format_id not in self.formats:
            self.formats[format_id] = {'count': 1, 'data': [(tile_id, data)]}
        elif self.formats[format_id]['count'] >= self.max_unique:
            return deepcopy(random.choice(self.formats[format_id]['data']))
        else:
            self.formats[format_id]['count'] += 1
            self.formats[format_id]['data'].append((tile_id, data))
    
    def burn_tile(self,location):
        if tuple(location) in self.grass_tiles: 
            #if the location does indeed have grass, burn the grass.
            self.grass_tiles[tuple(location)].burning = 0
        


    # attempt to place a new grass tile
    def place_tile(self, location, density, grass_options):
        # ignore if a tile was already placed in this location
        if tuple(location) not in self.grass_tiles:
            self.grass_tiles[tuple(location)] = GrassTile(self.tile_size, (location[0] * self.tile_size, location[1] * self.tile_size), density, grass_options, self.ga, self)

    # apply a force to the grass that causes the grass to bend away
    def apply_force(self, location, radius, dropoff):
        location = (int(location[0]), int(location[1]))
        grid_pos = (int(location[0] // self.tile_size), int(location[1] // self.tile_size))
        tile_range = math.ceil((radius + dropoff) / self.tile_size)
        for y in range(tile_range * 2 + 1):
            y = y - tile_range
            for x in range(tile_range * 2 + 1):
                x = x - tile_range
                pos = (grid_pos[0] + x, grid_pos[1] + y)
                if pos in self.grass_tiles:
                    self.grass_tiles[pos].apply_force(location, radius, dropoff)

    # an update and render combination function
    def update_render(self, surf, dt, offset=(0, 0), rot_function=None):
        visible_tile_range = (int(surf.get_width() // self.tile_size) + 1, int(surf.get_height() // self.tile_size) + 1)
        base_pos = (int(offset[0] // self.tile_size), int(offset[1] // self.tile_size))

        # get list of grass tiles to render based on visible area

        render_list = []
        for y in range(visible_tile_range[1]):
            for x in range(visible_tile_range[0]):
                pos = (base_pos[0] + x, base_pos[1] + y)
                if pos in self.grass_tiles:
                    render_list.append(pos)
        

        # render shadow if applicable
        if self.ground_shadow[0]:
            for pos in render_list:
                self.grass_tiles[pos].render_shadow(surf, offset=(offset[0] - self.ground_shadow[3][0], offset[1] - self.ground_shadow[3][1]))

        # render the grass tiles
        for pos in render_list:
            tile = self.grass_tiles[pos]
            if tile.burning == 0:

                #if the grass tile is burning, it checks for surrounding grass tiles. This range can be increased.
                #basic burn spread. 

                for offset_ in BURN_CHECK_OFFSETS:
                    check_pos = (pos[0] + offset_[0] , pos[1]+offset_[1] )
                    if check_pos in self.grass_tiles:
                        self.grass_tiles[check_pos].burning =  max(0,self.grass_tiles[check_pos].burning -1) 

            tile.render(surf, dt, offset=offset)
            if rot_function:
                tile.set_rotation(rot_function(tile.loc[0], tile.loc[1]),dt)

# an asset manager that contains functionality for rendering blades of grass
class GrassAssets:
    def __init__(self, path, gm):
        self.gm = gm
        self.blades = []

        # load in blade images
        for blade in sorted(os.listdir(path)):
            img = pygame.image.load(path + '/' + blade).convert()
            img.set_colorkey((0, 0, 0))
            

            #method of generating average rgb value of all the colored pixels in the image. 

            sum = [0,0,0]
            length = 0
            for x in range(0,img.get_width()):
                for y in range(0,img.get_height()):
                    
                    color = img.get_at((x,y))
                    if color != (0,0,0):
                        sum[0] += color[0] 
                        sum[1] += color[1]
                        sum[2] +=color[2] 
                        length+=1

            avg_color = (int(sum[0]/length),int(sum[1]/length),int(sum[2]/length))

            self.blades.append((img,avg_color))

        

    def render_blade(self, surf, blade_id, location, rotation,scale,palette):
        



        # rotate the blade
        rot_img = pygame.transform.rotate(self.blades[blade_id][0], rotation)

        #scale the image - won't scale if blade isn't burning. 
        rot_img = pygame.transform.scale(rot_img,(rot_img.get_width()*scale,rot_img.get_height()*scale))

        # shade the blade of grass based on its rotation
        shade = pygame.Surface(rot_img.get_size())
        shade_amt = self.gm.shade_amount * (abs(rotation) / 90)
        
        shade.set_alpha(shade_amt)

        #if the grass is burning, add a burning color to it. 
        if 0<scale < 1:
            red_mask = pygame.mask.from_surface(rot_img)

            #this set color algorithm? is just me messing around with numbers to see what gives the best outcome, closest to what I think looks like burning grass.
            red_mask.to_surface(rot_img,setcolor=(min(255,palette[0]*(1.8)*(1/scale*6)),min(255,palette[1] *(1/scale*1)) ,min(255,palette[2] *(1/scale*1))))
            
        

        rot_img.blit(shade, (0, 0))

        # render the blade
        surf.blit(rot_img, (location[0] - rot_img.get_width() // 2, location[1] - rot_img.get_height() // 2))

# the grass tile object that contains data for the blades
class GrassTile:
    def __init__(self, tile_size, location, amt, config, ga, gm):
        self.ga = ga
        self.gm = gm
        self.loc = location
        self.size = tile_size
        self.blades = []
        self.master_rotation = 0
        self.precision = 30
        self.padding = self.gm.padding
        self.inc = 90 / self.precision

        #max_burn_life is how long the grass will burn,  burn_life indicates how long the grass has burnt. 
        self.burn_life = 30
        self.max_burn_life = 30

        #when this becomes 0, the grass will start to burn. 
        self.burning = 60

        # generate blade data
        y_range = self.gm.vertical_place_range[1] - self.gm.vertical_place_range[0]
        for i in range(amt):
            new_blade = random.choice(config)


            #img is a tuple, (img,color) 
            img = self.ga.blades[new_blade]
            
            y_pos = self.gm.vertical_place_range[0]
            if y_range:
                y_pos = random.random() * y_range + self.gm.vertical_place_range[0]

            #the average rgb value or the 'general color' of the blade image is added to the blade data. - img[1]
            self.blades.append([(random.random() * self.size, y_pos * self.size), new_blade, random.random() * 30 - 15,img[1]])

        # layer back to front
        self.blades.sort(key=lambda x: x[1])

        # get next ID
        self.base_id = self.gm.grass_id
        self.gm.grass_id += 1

        # check if the blade data needs to be overwritten with a previous layout to save RAM usage
        format_id = (amt, tuple(config))
        overwrite = self.gm.get_format(format_id, self.blades, self.base_id)
        if overwrite:
            self.blades = overwrite[1]
            self.base_id = overwrite[0]

        # custom_blade_data is used when the blade's current state should not be cached. all grass tiles will try to return to a cached state
        self.custom_blade_data = None

        self.update_render_data(0)
       

    # apply a force that affects each blade individually based on distance instead of the rotation of the entire tile
    def apply_force(self, force_point, force_radius, force_dropoff):
        if not self.custom_blade_data:
            self.custom_blade_data = [None] * len(self.blades)

        for i, blade in enumerate(self.blades):
            orig_data = self.custom_blade_data[i]
            dis = math.sqrt((self.loc[0] + blade[0][0] - force_point[0]) ** 2 + (self.loc[1] + blade[0][1] - force_point[1]) ** 2)
            max_force = False
            if dis < force_radius:
                force = 2
            else:
                dis = max(0, dis - force_radius)
                force = 1 - min(dis / force_dropoff, 1)
            dir = 1 if force_point[0] > (self.loc[0] + blade[0][0]) else -1
            # don't update unless force is greater
            if not self.custom_blade_data[i] or abs(self.custom_blade_data[i][2] - self.blades[i][2]) <= abs(force) * 90:
                self.custom_blade_data[i] = [blade[0], blade[1], blade[2] + dir * force * 90,blade[3]]



    # update the identifier used to find a valid cached image
    def update_render_data(self,dt):


        #the grass starts burning when self.burning is 0. This is done so that the burn spread doesn't happen immediately. 

        if self.burning == 0:
            self.burn_life = max(0,self.burn_life - 25 * dt)

            #if the grass has burnt out completely, then get rid of the grass from the grasstiles list 
            if self.burn_life  == 0:
                self.blades = [None] * len(self.blades)
                check_loc = (self.loc[0]//self.size,self.loc[1]//self.size)
                del self.gm.grass_tiles[check_loc]
                del self
                
        else: 

        #basically updates rotation 
        
            self.render_data = (self.base_id, self.master_rotation)
            self.true_rotation = self.inc * self.master_rotation

    # set new master tile rotation
    def set_rotation(self, rotation,dt):
        self.master_rotation = rotation
        self.update_render_data(dt)

    # render the tile's image based on its current state and return the data
    def render_tile(self, render_shadow=False):
        # make a new padded surface (to fit blades spilling out of the tile)
        surf = pygame.Surface((self.size + self.padding * 2, self.size + self.padding * 2))
        surf.set_colorkey((0, 0, 0))



        # use custom_blade_data if it's active (uncached). otherwise use the base data (cached).
        if self.custom_blade_data:
            blades = self.custom_blade_data
        else:
            blades = self.blades
        
        # render the shadows of each blade if applicable
        if render_shadow:
            shadow_surf = pygame.Surface(surf.get_size())
            shadow_surf.set_colorkey((0, 0, 0))
            for blade in self.blades:
                pygame.draw.circle(shadow_surf, self.gm.ground_shadow[1], (blade[0][0] + self.padding, blade[0][1] + self.padding), self.gm.ground_shadow[0])
            shadow_surf.set_alpha(self.gm.ground_shadow[2])

       
        # render each blade using the asset manager
        # the last two parameters: self.burn_life/self.max_burn_life,blade[3] is the scale of which the blade will be scaled down to, and the color of that blade. 
        # the scale will always be 1 when the grass isn't burning, and will decrease when it starts to . The color data is needed to add a burn shade effect. 

        for blade in blades:
            self.ga.render_blade(surf, blade[1], (blade[0][0] + self.padding, blade[0][1] + self.padding), max(-90, min(90, blade[2] + self.true_rotation)),self.burn_life/self.max_burn_life,blade[3])

        # return surf and shadow_surf if applicable
        if render_shadow:
            return surf, shadow_surf
        else:
            return surf

    # draw the shadow image for the tile
    def render_shadow(self, surf, offset=(0, 0)):
        if self.gm.ground_shadow[0] and (self.base_id in self.gm.shadow_cache):
            surf.blit(self.gm.shadow_cache[self.base_id], (self.loc[0] - offset[0] - self.padding, self.loc[1] - offset[1] - self.padding))


    # draw the grass itself

    def render(self, surf, dt, offset=(0, 0)):
        # render a new grass tile image if using custom uncached data otherwise use cached data if possible Also, if the tile is burning, don't use 
        # cached data. 

        if self.burning == 0: 
            #if it is burning, no caaache. Performance? well, the grass will be deleted after the burn duration, so performace shouldn't be a big issue. 
            img = self.render_tile() 
            surf.blit(img, (self.loc[0] - offset[0] - self.padding, self.loc[1] - offset[1] - self.padding))
        else: 

        
            if self.custom_blade_data:
                 
                    img = self.render_tile() 
                    surf.blit(img, (self.loc[0] - offset[0] - self.padding, self.loc[1] - offset[1] - self.padding))
                    
            else:
                # check if a new cached image needs to be generated and use the cached data if not (also cache shadow if necessary)
                if (self.render_data not in self.gm.grass_cache) and (self.gm.ground_shadow[0] and (self.base_id not in self.gm.shadow_cache)):
                    grass_img, shadow_img = self.render_tile(render_shadow=True)
                    self.gm.grass_cache[self.render_data] = grass_img
                    self.gm.shadow_cache[self.base_id] = shadow_img
                elif self.render_data not in self.gm.grass_cache:
                    self.gm.grass_cache[self.render_data] = self.render_tile()
               
                
                surf.blit(self.gm.grass_cache[self.render_data], (self.loc[0] - offset[0] - self.padding, self.loc[1] - offset[1] - self.padding))

        # attempt to move blades back to their base position
        if self.custom_blade_data:
            matching = True
            for i, blade in enumerate(self.custom_blade_data):
                blade[2] = normalize(blade[2], self.gm.stiffness * dt, self.blades[i][2])
                if blade[2] != self.blades[i][2]:
                    matching = False
            # mark the data as non-custom once in base position so the cache can be used
            if matching:
                self.custom_blade_data = None

       
