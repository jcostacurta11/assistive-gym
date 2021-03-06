import os, time
from gym import spaces
import numpy as np
import pybullet as p
import matplotlib.pyplot as plt

from .env import AssistiveEnv

class BiteTransferEnv(AssistiveEnv):

    def __init__(self, robot_type='panda', human_control=False, width=256, height=256):
        super(BiteTransferEnv, self).__init__(robot_type=robot_type, task='bite_transfer', human_control=human_control,
                                              frame_skip=10, time_step=0.01, action_robot_len=7,
                                              action_human_len=(4 if human_control else 0), obs_robot_len=25,
                                              obs_human_len=(23 if human_control else 0))
        self.foods = ['strawberry.urdf', 'carrot.urdf']

        self.fov = 60
        self.near = 0.005
        self.far = 0.1
        self.yaw, self.pitch, self.roll = 60, 0, 0

        self.camdist = 0.05
        self.img_width, self.img_height = width, height

        self.fig, self.ax = plt.subplots(nrows=2, ncols=2, figsize=(10, 10))
        self.im1 = self.ax[0, 0].imshow(np.zeros((width, height, 4)))
        self.im2 = self.ax[0, 1].imshow(np.zeros((width, height, 4)))
        self.im1_d = self.ax[1, 0].imshow(np.zeros((width, height, 4)), cmap='gray', vmin=0, vmax=1)
        self.im2_d = self.ax[1, 1].imshow(np.zeros((width, height, 4)), cmap='gray', vmin=0, vmax=1)

    # TODO
    def step(self, action, ret_images=False):
        # actually step in the environment
        self.take_step(action, robot_arm='right', gains=self.config('robot_gains'), forces=self.config('robot_forces'),
                       human_gains=0.0005)

        end_effector_velocity = np.linalg.norm(p.getBaseVelocity(self.drop_fork, physicsClientId=self.id)[0])
        obs = self._get_obs(ret_images=ret_images)

        reward = 0

        if self.gui and reward != 0:
            print('Task success:', self.task_success, 'Food reward:', reward)

        info = {'total_force_on_human': 0, 'task_success': 0, 'action_robot_len': self.action_robot_len,
                'action_human_len': self.action_human_len, 'obs_robot_len': self.obs_robot_len,
                'obs_human_len': self.obs_human_len}
        done = False

        return obs, reward, done, info

    def get_total_force(self):
        # TODO haptic?
        robot_force_on_mouth = 0.
        fork_force_on_mouth = 0.
        food_force_on_mouth = 0.
        for c in p.getContactPoints(bodyA=self.robot, bodyB=self.mouth, physicsClientId=self.id):
            robot_force_on_mouth += c[9]
        for c in p.getContactPoints(bodyA=self.drop_fork, bodyB=self.human, physicsClientId=self.id):
            fork_force_on_mouth += c[9]
        for c in p.getContactPoints(bodyA=self.foodItem, bodyB=self.human, physicsClientId=self.id):
            food_force_on_mouth += c[9]
        return [robot_force_on_mouth, fork_force_on_mouth, food_force_on_mouth]

    def _get_obs(self, forces=None, ret_images=False):
        fork_pos, fork_orient = p.getBasePositionAndOrientation(self.drop_fork, physicsClientId=self.id)
        food_pos, food_orient = p.getBasePositionAndOrientation(self.foodItem, physicsClientId=self.id)
        robot_right_joint_states = p.getJointStates(self.robot, jointIndices=self.robot_right_arm_joint_indices,
                                                    physicsClientId=self.id)
        robot_right_joint_positions = np.array([x[0] for x in robot_right_joint_states])
        robot_pos, robot_orient = p.getBasePositionAndOrientation(self.robot, physicsClientId=self.id)

        # get forces if not precomputed
        if forces is None:
            forces = self.get_total_force()  # robot, fork, food

        robot_obs = np.concatenate([
            robot_right_joint_positions,
            fork_pos,  # 3D drop fork position
            fork_orient,  # drop fork orientation
            food_pos,  # 3D food position
            food_orient,  # food orientation (absolute)
            self.food_orient_quat,  # food orientation (relative to fork)
            [self.food_type],  # food type
            self.mouth_pos,  # 3D mouth center pos (target)
            self.mouth_orient,  # mouth orientation (absolute)
            forces]).ravel().astype(np.float32)

        if ret_images:
            return robot_obs, self.depth_opengl1, self.depth_opengl2
        return robot_obs

    def render(self, mode='human'):
        pg = self.gui

        super(BiteTransferEnv, self).render(mode)

        if not pg and self.gui:
            print("Showing plot")
            plt.show(block=False)
            self.fig.canvas.draw()

    def reset(self, ret_images=False):
        self.setup_timing()
        self.task_success = 0
        self.human, self.wheelchair, self.robot, self.robot_lower_limits, self.robot_upper_limits, self.human_lower_limits, self.human_upper_limits, self.robot_right_arm_joint_indices, self.robot_left_arm_joint_indices, self.gender = self.world_creation.create_new_world(
            furniture_type='wheelchair', static_human_base=True, human_impairment='random', print_joints=False,
            gender='random')
        self.robot_lower_limits = self.robot_lower_limits[self.robot_right_arm_joint_indices]
        self.robot_upper_limits = self.robot_upper_limits[self.robot_right_arm_joint_indices]
        self.reset_robot_joints()
        #
        # if self.robot_type == 'jaco':
        #     wheelchair_pos, wheelchair_orient = p.getBasePositionAndOrientation(self.wheelchair,
        #                                                                         physicsClientId=self.id)
        #     p.resetBasePositionAndOrientation(self.robot, np.array(wheelchair_pos) + np.array([-0.35, -0.3, 0.3]),
        #                                       p.getQuaternionFromEuler([0, 0, -np.pi / 2.0], physicsClientId=self.id),
        #                                       physicsClientId=self.id)
        #     base_pos, base_orient = p.getBasePositionAndOrientation(self.robot, physicsClientId=self.id)

        joints_positions = [(6, np.deg2rad(-90)), (16, np.deg2rad(-90)), (28, np.deg2rad(-90)), (31, np.deg2rad(80)),
                            (35, np.deg2rad(-90)), (38, np.deg2rad(80))]
        joints_positions += [(21, self.np_random.uniform(np.deg2rad(-30), np.deg2rad(30))),
                             (22, self.np_random.uniform(np.deg2rad(-30), np.deg2rad(30))),
                             (23, self.np_random.uniform(np.deg2rad(-30), np.deg2rad(30)))]
        self.human_controllable_joint_indices = [20, 21, 22, 23]
        self.world_creation.setup_human_joints(self.human, joints_positions, self.human_controllable_joint_indices if (
                self.human_control or self.world_creation.human_impairment == 'tremor') else [],
                                               use_static_joints=True, human_reactive_force=None)
        p.resetBasePositionAndOrientation(self.human, [0, 0.03, 0.89 if self.gender == 'male' else 0.86], [0, 0, 0, 1],
                                          physicsClientId=self.id)
        human_joint_states = p.getJointStates(self.human, jointIndices=self.human_controllable_joint_indices,
                                              physicsClientId=self.id)
        self.target_human_joint_positions = np.array([x[0] for x in human_joint_states])
        self.human_lower_limits = self.human_lower_limits[self.human_controllable_joint_indices]
        self.human_upper_limits = self.human_upper_limits[self.human_controllable_joint_indices]

        # Place a bowl of food on a table
        self.table = p.loadURDF(os.path.join(self.world_creation.directory, 'table', 'table_tall.urdf'),
                                basePosition=[0.35, -0.9, 0],
                                baseOrientation=p.getQuaternionFromEuler([0, 0, 0], physicsClientId=self.id),
                                physicsClientId=self.id)

        # MOUTH SIM
        self.mouth_pos = [-0, -0.15, 1.4]
        self.mouth_orient = p.getQuaternionFromEuler([np.pi / 2, np.pi / 2, -np.pi / 2], physicsClientId=self.id)

        self.mouth = p.loadURDF(os.path.join(self.world_creation.directory, 'mouth', 'hole.urdf'), useFixedBase=True,
                                basePosition=self.mouth_pos,
                                baseOrientation=self.mouth_orient,
                                flags=p.URDF_USE_SELF_COLLISION, physicsClientId=self.id)

        # SCALE = 0.1
        # self.mouthVisualShapeId = p.createVisualShape(shapeType=p.GEOM_MESH,
        #                                               fileName=os.path.join(self.world_creation.directory, 'mouth', 'hole2.obj'),
        #                                               rgbaColor=[0.8, 0.4, 0, 1],
        #                                               # specularColor=[0.4, .4, 0],
        #                                               visualFramePosition=[0, 0, 0],
        #                                               meshScale=[SCALE] * 3,
        #                                               physicsClientId=self.id)
        # self.mouthCollisionShapeId = p.createCollisionShape(shapeType=p.GEOM_MESH,
        #                                                     fileName=os.path.join(self.world_creation.directory, 'mouth', 'hole2.obj'),
        #                                                     collisionFramePosition=[0, 0, 0],
        #                                                     meshScale=[SCALE] * 3,
        #                                                     flags=p.GEOM_FORCE_CONCAVE_TRIMESH,
        #                                                     physicsClientId=self.id)
        # self.mouth = p.createMultiBody(baseMass=0.1,
        #                                baseInertialFramePosition=[0, 0, 0],
        #                                baseCollisionShapeIndex=self.mouthCollisionShapeId,
        #                                baseVisualShapeIndex=self.mouthVisualShapeId,
        #                                basePosition=[0, 0, 0],
        #                                useMaximalCoordinates=True,
        #                                flags=p.URDF_USE_SELF_COLLISION,
        #                                physicsClientId=self.id)

        p.resetDebugVisualizerCamera(cameraDistance=1.10, cameraYaw=40, cameraPitch=-45,
                                     cameraTargetPosition=[-0.2, 0, 0.75], physicsClientId=self.id)
        # ROBOT STUFF
        # target_pos = np.array(bowl_pos) + np.array([0, -0.1, 0.4]) + self.np_random.uniform(-0.05, 0.05, size=3)
        if self.robot_type == 'panda':
            # target_pos = [0.2, -0.7, 1.4]
            # target_orient = [-0.7350878727462702, -8.032928869253401e-09, 7.4087721728719465e-09,
            #                  0.6779718425874067]
            # target_orient = [0.4902888273008801, -0.46462044731135954, -0.5293302738768326, -0.5133752690981496]
            # target_orient = p.getQuaternionFromEuler(np.array([0, 0, np.pi / 2.0]), physicsClientId=self.id)
            # self.util.ik_random_restarts(self.robot, 8, target_pos, target_orient, self.world_creation,
            #                              self.robot_right_arm_joint_indices, self.robot_lower_limits,
            #                              self.robot_upper_limits,
            #                              ik_indices=range(len(self.robot_right_arm_joint_indices)), max_iterations=1000,
            #                              max_ik_random_restarts=40, random_restart_threshold=0.01, step_sim=True,
            #                              check_env_collisions=True)
            #
            positions = [0.42092164, -0.92326318, -0.33538581, -2.65185322, 1.40763901, 1.81818155, 0.58610855, 0, 0,
                         0.02, 0.02]  # 11
            for idx in range(len(positions)):
                p.resetJointState(self.robot, idx, positions[idx])

            self.world_creation.set_gripper_open_position(self.robot, position=0.00, left=False, set_instantly=True)
            self.drop_fork = self.world_creation.init_tool(self.robot, mesh_scale=[0.08] * 3,
                                                           pos_offset=[0, 0, 0.08],  # fork: [0, -0.02, 0.16],
                                                           orient_offset=p.getQuaternionFromEuler([-0, -np.pi, 0],
                                                                                                  physicsClientId=self.id),
                                                           left=False, maximal=False)
        else:
            raise NotImplementedError

        # LOAD FOOD ITEM
        self.food_type = np.random.randint(0, len(self.foods), dtype=int)
        print("LOADING food file: %s" % self.foods[self.food_type])
        self.childZ = [-0.004, -0.0065]
        self.foodOrientEul = np.random.rand(3) * 2 * np.pi
        self.food_orient_quat = p.getQuaternionFromEuler(self.foodOrientEul, physicsClientId=self.id)
        self.foodItem = p.loadURDF(
            os.path.join(self.world_creation.directory, 'food_items', self.foods[self.food_type]),
            basePosition=[0, 0, 0],
            baseOrientation=p.getQuaternionFromEuler([0, 0, 0],
                                                     physicsClientId=self.id),
            physicsClientId=self.id)

        # Disable collisions between the tool and food item
        for ti in list(range(p.getNumJoints(self.drop_fork, physicsClientId=self.id))) + [-1]:
            for tj in list(range(p.getNumJoints(self.foodItem, physicsClientId=self.id))) + [-1]:
                p.setCollisionFilterPair(self.drop_fork, self.foodItem, ti, tj, False, physicsClientId=self.id)

        # Create constraint that keeps the food item in the tool
        constraint = p.createConstraint(self.drop_fork, -1,
                                        self.foodItem, -1, p.JOINT_FIXED, jointAxis=[0, 0, 0],
                                        parentFramePosition=[0, 0, -0.025],
                                        childFramePosition=[0, 0, self.childZ[self.food_type]],
                                        parentFrameOrientation=self.food_orient_quat,
                                        childFrameOrientation=[0, 0, 0, 1],
                                        physicsClientId=self.id)
        p.changeConstraint(constraint, maxForce=500, physicsClientId=self.id)

        # p.resetBasePositionAndOrientation(self.bowl, bowl_pos, p.getQuaternionFromEuler([np.pi/2.0, 0, 0], physicsClientId=self.id), physicsClientId=self.id)

        p.setGravity(0, 0, -9.81, physicsClientId=self.id)
        p.setGravity(0, 0, 0, body=self.robot, physicsClientId=self.id)
        p.setGravity(0, 0, 0, body=self.human, physicsClientId=self.id)

        p.setPhysicsEngineParameter(numSubSteps=5, numSolverIterations=10, physicsClientId=self.id)

        # Enable rendering

        p.configureDebugVisualizer(p.COV_ENABLE_RENDERING, 1, physicsClientId=self.id)
        # init_pos = [0.0, 0.0, 0.0, -2 * np.pi / 4, 0.0, np.pi / 2, np.pi / 4, 0.0, 0.0, 0.05, 0.05]
        # self._reset_robot(init_pos)

        # initialize images
        for i in range(10):
            p.stepSimulation()

        ee_pos, ee_orient = p.getBasePositionAndOrientation(self.foodItem)
        self.viewMat1 = p.computeViewMatrixFromYawPitchRoll(ee_pos, self.camdist, self.yaw, self.pitch, self.roll, 2, self.id)
        self.viewMat2 = p.computeViewMatrixFromYawPitchRoll(ee_pos, self.camdist, -self.yaw, self.pitch, self.roll, 2, self.id)
        self.projMat = p.computeProjectionMatrixFOV(self.fov, self.img_width / self.img_height, self.near, self.far)

        images1 = p.getCameraImage(self.img_width,
                                   self.img_height,
                                   self.viewMat1,
                                   self.projMat,
                                   shadow=True,
                                   renderer=p.ER_BULLET_HARDWARE_OPENGL,
                                   physicsClientId=self.id)
        images2 = p.getCameraImage(self.img_width,
                                   self.img_height,
                                   self.viewMat2,
                                   self.projMat,
                                   shadow=True,
                                   renderer=p.ER_BULLET_HARDWARE_OPENGL,
                                   physicsClientId=self.id)
        self.rgb_opengl1 = np.reshape(images1[2], (self.img_width, self.img_height, 4)) * 1. / 255.
        depth_buffer_opengl = np.reshape(images1[3], [self.img_width, self.img_height])
        self.depth_opengl1 = self.far * self.near / (self.far - (self.far - self.near) * depth_buffer_opengl)

        self.rgb_opengl2 = np.reshape(images2[2], (self.img_width, self.img_height, 4)) * 1. / 255.
        depth_buffer_opengl = np.reshape(images2[3], [self.img_width, self.img_height])
        self.depth_opengl2 = self.far * self.near / (self.far - (self.far - self.near) * depth_buffer_opengl)

        if self.gui:
            # TODO: do we need to update this every step? prob not
            self.im1.set_data(self.rgb_opengl1)
            self.im2.set_data(self.rgb_opengl2)
            self.im1_d.set_data(self.depth_opengl1)
            self.im2_d.set_data(self.depth_opengl2)
            self.fig.canvas.draw()

        return self._get_obs(ret_images=ret_images)

    def _reset_robot(self, joint_position):
        self.state = {}
        self.jacobian = {}
        self.desired = {}
        for idx in range(len(joint_position)):
            p.resetJointState(self.robot, idx, joint_position[idx])
        self._read_state()
        self._read_jacobian()
        self.desired['joint_position'] = self.state['joint_position']
        self.desired['ee_position'] = self.state['ee_position']
        self.desired['ee_quaternion'] = self.state['ee_quaternion']

    def update_targets(self):
        pass
        # head_pos, head_orient = p.getLinkState(self.human, 23, computeForwardKinematics=True, physicsClientId=self.id)[
        #                         :2]
        # target_pos, target_orient = p.multiplyTransforms(head_pos, head_orient, self.mouth_pos, [0, 0, 0, 1],
        #                                                  physicsClientId=self.id)
        # self.target_pos = np.array(target_pos)

    # copied from panda-env repo
    def _read_jacobian(self):
        linear_jacobian, angular_jacobian = p.calculateJacobian(self.robot, 11, [0, 0, 0],
                                                                list(self.state['joint_position']), [0] * 9, [0] * 9)
        linear_jacobian = np.asarray(linear_jacobian)[:, :7]
        angular_jacobian = np.asarray(angular_jacobian)[:, :7]
        full_jacobian = np.zeros((6, 7))
        full_jacobian[0:3, :] = linear_jacobian
        full_jacobian[3:6, :] = angular_jacobian
        self.jacobian['full_jacobian'] = full_jacobian
        self.jacobian['linear_jacobian'] = linear_jacobian
        self.jacobian['angular_jacobian'] = angular_jacobian

    def _read_state(self):
        joint_position = [0] * 9
        joint_velocity = [0] * 9
        joint_torque = [0] * 9
        joint_states = p.getJointStates(self.robot, range(9))
        for idx in range(9):
            joint_position[idx] = joint_states[idx][0]
            joint_velocity[idx] = joint_states[idx][1]
            joint_torque[idx] = joint_states[idx][3]
        ee_states = p.getLinkState(self.robot, 11)
        ee_position = list(ee_states[4])
        ee_quaternion = list(ee_states[5])
        gripper_contact = p.getContactPoints(bodyA=self.robot, linkIndexA=10)
        self.state['joint_position'] = np.asarray(joint_position)
        self.state['joint_velocity'] = np.asarray(joint_velocity)
        self.state['joint_torque'] = np.asarray(joint_torque)
        self.state['ee_position'] = np.asarray(ee_position)
        self.state['ee_quaternion'] = np.asarray(ee_quaternion)
        self.state['ee_euler'] = np.asarray(p.getEulerFromQuaternion(ee_quaternion))
        self.state['gripper_contact'] = len(gripper_contact) > 0

    def _inverse_kinematics(self, ee_position, ee_quaternion):
        return p.calculateInverseKinematics(self.robot, 11, list(ee_position), list(ee_quaternion))

    def _velocity_control(self, mode, djoint, dposition, dquaternion, grasp_open):
        if mode:
            self.desired['ee_position'] += np.asarray(dposition) / 240.0
            self.desired['ee_quaternion'] += np.asarray(dquaternion) / 240.0
            q_dot = self._inverse_kinematics(self.desired['ee_position'], self.desired['ee_quaternion']) - self.state[
                'joint_position']
        else:
            self.desired['joint_position'] += np.asarray(list(djoint) + [0, 0]) / 240.0
            q_dot = self.desired['joint_position'] - self.state['joint_position']
        gripper_position = [0.0, 0.0]
        if grasp_open:
            gripper_position = [0.05, 0.05]
        p.setJointMotorControlArray(self.robot, range(9), p.VELOCITY_CONTROL, targetVelocities=list(q_dot))
        p.setJointMotorControlArray(self.robot, [9, 10], p.POSITION_CONTROL, targetPositions=gripper_position)
