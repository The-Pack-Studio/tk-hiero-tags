# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import hiero.core

from tank.platform import Application
from tank import TankError
from tank.platform.qt import QtGui, QtCore
from pprint import pprint



class HieroShotgridTags(Application):


    def init_app(self):
        """
        Initialization
        """

        self.engine.register_command("Sync project tags with Shotgun", self.project_tags_sync )

        self.engine.register_command("Push tags to SG (add)", self.tags_push_add, {"icon": os.path.join(os.path.dirname(__file__), 'icon_push_256.png')})
        self.engine.register_command("Push tags to SG (overwrite)", self.tags_push_overwrite, {"icon": os.path.join(os.path.dirname(__file__), 'icon_push_256.png')} )
        self.engine.register_command("Pull tags from SG (add)", self.tags_pull_add, {"icon": os.path.join(os.path.dirname(__file__), 'icon_pull_256.png')} )
        self.engine.register_command("Pull tags from SG (overwrite)", self.tags_pull_overwrite, {"icon": os.path.join(os.path.dirname(__file__), 'icon_pull_256.png')})


    @property
    def context_change_allowed(self):
        """
        Specifies that context changes are allowed.
        """
        return True

    def project_tags_sync(self):
        """
        Syncs shotgun project tags with Hiero project tags
        Sends hiero tags to shotgun project tags and vice-versa. 
        Only adds in both direction, never deletes
        """

        tk = self.sgtk
        context = self.context


        # all custom project tags of Hiero project 
        hiero_project_tags = hiero.core.findProjectTags()
        hiero_project_tags = self._filter_hiero_tags(hiero_project_tags)

        # query sg for all the tags in this project
        filters = [["project", "is", context.project]]
        fields = ["id", "code"]
        sg_project_tags = tk.shotgun.find('CustomEntity05', filters=filters, fields=fields)

        # Build list of missing shotgun project tags
        hiero_only_tags = []
        for hiero_tag in hiero_project_tags:
            for sg_project_tag in sg_project_tags:
                if hiero_tag.name() == sg_project_tag['code']:
                    break
            else:
                hiero_only_tags.append(hiero_tag)

        # Build list of missing hiero tags
        sg_only_tags = []
        for sg_project_tag in sg_project_tags:
            for hiero_tag in hiero_project_tags:
                if sg_project_tag['code'] == hiero_tag.name():
                    break
            else:
                sg_only_tags.append(sg_project_tag)


        # Create missing tags in Shotgun
        for hiero_tag in hiero_only_tags:

            data = { "project": context.project,
                     "code": hiero_tag.name(),
                     }
            new_sg_tag = tk.shotgun.create("CustomEntity05", data)
            self.log_debug("Hiero project tags '%s' created in SG" % hiero_tag.name())

        # Create missing tags in Hiero
        for sg_tag in sg_only_tags:

            new_hiero_tag = hiero.core.Tag(sg_tag["code"])
            hiero_project = hiero.core.projects()[-1]
            hiero_project.tagsBin().addItem(new_hiero_tag) 
            self.log_debug("Shotgun project tag '%s' created in Hiero" % sg_tag["code"])



    def tags_push_add(self):
        self.track_item_tag_sync(direction="push", overwrite=False)

    def tags_push_overwrite(self):
        self.track_item_tag_sync(direction="push", overwrite=True)

    def tags_pull_add(self):
        self.track_item_tag_sync(direction="pull", overwrite=False)

    def tags_pull_overwrite(self):
        self.track_item_tag_sync(direction="pull", overwrite=True)





    def track_item_tag_sync(self, direction="", overwrite=False):

        tk = self.sgtk
        context = self.context

        track_items = self._selected_track_items()

        # query sg for all the shots of this project
        filters = [["project", "is", context.project]]
        fields = ["code", "sg_project_tags", "sg_sequence"]
        sg_shots = tk.shotgun.find('Shot', filters=filters, fields=fields)

        # query sg for all the tags in this project
        filters = [["project", "is", context.project]]
        fields = ["id", "code"]
        sg_project_tags = tk.shotgun.find('CustomEntity05', filters=filters, fields=fields)


        for track_item in track_items:

            # find the corresponding shot in shotgun
            track_item_name = track_item.name()
            shotname_parts = track_item_name.split("_") # if no underscore, will return whole name

            if len(shotname_parts) != 2:
                self.log_error("Trackitem '%s' is not composed of two parts separated by an underscore. Can't find shot name." % track_item_name)
                # should append this to a list of errors and diplay it after the loop is finished ?
                # QtGui.QMessageBox.critical(None, "Shot Lookup Error!", "Trackitem '%s' is not composed of two parts separated by an underscore. Can't find shot name." % track_item_name)
                continue

            sequence_name = shotname_parts[0]
            shot_name = shotname_parts[1]

            target_sg_shot =  None
            for sg_shot in sg_shots:
                if sg_shot["code"] == shot_name and sg_shot["sg_sequence"]["name"] == sequence_name:
                    target_sg_shot = sg_shot
                    break

            if not target_sg_shot:
                self.log_error("Trackitem '%s' doesn't seem to exist in Shotgrid" % track_item_name)
                continue

            #if we are here it means we have a correctly named track item and a corresponding shotgun shot
            # self.log_debug("Found shotgun shot : %s corresponding to track item %s" % (target_sg_shot, track_item_name))

            # get the tags from this hiero track item
            hiero_item_tags = self._filter_hiero_tags(track_item.tags())

            # get the tags from this shotgrid shot
            for sg_shot in sg_shots:
                if sg_shot["id"] == target_sg_shot["id"]:
                    sg_shot_tags = sg_shot["sg_project_tags"]
                    break


            if direction == "push":

                if overwrite:
                    # first need to remove all tags from that shot in shotgun
                    tk.shotgun.update(target_sg_shot["type"], target_sg_shot["id"], {"sg_project_tags" : []})
                    self.log_debug("Overwrite asked: Clearing existing tags on SG shot %s" % target_sg_shot["code"])
        

                target_sg_tags = [] #empty list of shotgun project tags

                for hiero_item_tag in hiero_item_tags:
                    target_sg_tag = None
                    for sg_project_tag in sg_project_tags:
                        if hiero_item_tag.name() == sg_project_tag["code"]:
                            target_sg_tag = sg_project_tag

                    if not target_sg_tag: # that hiero tag doesn't have a corresponding Shotgun project tag, need to create it
                        data = { "project": context.project, "code": hiero_item_tag.name() }
                        target_sg_tag = tk.shotgun.create("CustomEntity05", data)
                        self.log_debug("Hiero tag %s has no equivalent in the SG project tags. Created new SG project tag %s" % (hiero_item_tag.name(), target_sg_tag["code"])  )

                    # now we have a corresponding shotgun tag, append it to a list of tags
                    target_sg_tags.append(target_sg_tag)

                # Update the sg shot to add all the tags to it in one go.
                tk.shotgun.update(target_sg_shot["type"],
                                    target_sg_shot["id"],
                                    {"sg_project_tags" : target_sg_tags},
                                    multi_entity_update_modes={"sg_project_tags": "add"}
                                    )

                self.log_debug("Pushed Hiero tags to SG. Shotgrid Project tags: %s were added to the SG Shot %s" % ([t['code'] for t in target_sg_tags], target_sg_shot['code']) )



            if direction == "pull":

                if overwrite: # need to remove all tags from the track item
                    for t in hiero_item_tags:
                       track_item.removeTag(t)
                    hiero_item_tags = self._filter_hiero_tags(track_item.tags())

                hiero_item_tags_names = [ht.name() for ht in hiero_item_tags]
                for sg_shot_tag in sg_shot_tags:
                    if not sg_shot_tag["name"] in hiero_item_tags_names:
                        #need to add a tag
                        new_hiero_tag = hiero.core.Tag(sg_shot_tag["name"])
                        track_item.addTag(new_hiero_tag)
                        # Lets also add this new tag to the bin tags, if it doesn't exist yet
                        hiero_project_tags = hiero.core.findProjectTags()
                        hiero_project_tags = self._filter_hiero_tags(hiero_project_tags)
                        for hiero_project_tag in hiero_project_tags:
                            if hiero_project_tag.name() == new_hiero_tag.name():
                                break
                        else : # didn't find a identical tag in the tags bin, add it
                            hiero_project = hiero.core.projects()[-1] 
                            hiero_project.tagsBin().addItem(new_hiero_tag) #also add it to the tags bin


    def _selected_track_items(self):
        """
        from the current selection, filter to keep only track items
        """

        # grab the current selection from the view that triggered the event.
        selection = self.engine.get_menu_selection()


        # Exclude transisions from the list of selected items if this version of
        # hiero supports effects
        if hasattr(hiero.core, "Transition"):
            selection = [
                s for s in selection if not isinstance(s, hiero.core.Transition)
            ]

        # Exclude effects from the list of selected items if this version of
        # hiero supports effects
        if hasattr(hiero.core, "EffectTrackItem"):
            selection = [
                s for s in selection if not isinstance(s, hiero.core.EffectTrackItem)
            ]

        return selection

    def _filter_hiero_tags(self, tags):
        """
        input : list of tags
        output : list of tags excluding auto generated ones and ones starting with "shotguntype="
        """

        filtered_tags = []

        for tag in tags:
            if "shotguntype" in tag.name():
                continue
            if "Transcode" in tag.name():
                continue
            if "Nuke Project File" in tag.name():
                continue
            filtered_tags.append(tag)

        return filtered_tags        

