# Localize DBS Electrodes 视图判读与电极定位教程

本文记录 Lead-DBS `Localize DBS electrodes` 手动复核窗口中各个视图的含义，以及如何综合这些视图选择更合理的电极 head、tail 和轴线位置。

## 入口与窗口

在 Lead-DBS 主界面的 `2. Localization` 页中，勾选 `Localize DBS electrodes` 后点击 `Run`，会打开手动复核窗口。该窗口的核心任务是检查并修正电极重建结果。

窗口里通常包括：

- 左侧电极模型示意图：显示当前电极型号、contacts、head 和 tail 的相对结构。
- `ANTERIOR VIEW`：从前方观察的纵向重采样视图。
- `LEFT VIEW`：从左侧观察的同一组纵向重采样视图。
- `DORSAL VIEW`：head 和 tail 附近的局部横断面视图。
- 红色星号：head / distal marker。
- 绿色星号：tail / proximal marker。
- 紫色圆圈：根据当前 head、tail、电极型号推算出的 contacts。
- 蓝色线：当前 head-tail 定义的电极轴线或重建轨迹。

## ANTERIOR VIEW 的含义

`ANTERIOR VIEW` 不是普通固定冠状切片。它是围绕当前电极轨迹生成的纵向重采样视图，然后从前方显示。

可以把当前电极轴线写成：

```text
C(s)
```

其中 `s` 表示沿电极从 head 到 tail 的位置。Lead-DBS 会围绕这条轴线生成两张纵向 surface：

```text
C(s) + u * [1, 0, 0]
C(s) + u * [0, 1, 0]
```

这里 `u` 是离开电极轴线的横向距离。第一张面沿左右方向展开，第二张面沿前后方向展开。两张面都穿过电极轴线，形成类似十字形的纵向采样。随后窗口用 anterior camera view 显示这些 surface。

实际判读时，应关注：

- 蓝色轴线是否沿金属伪影柱的中心走。
- 紫色 contacts 是否大致落在伪影柱中线。
- 红绿点是否位于电极伪影末端和近端的合理位置。
- 如果伪影柱与蓝线有夹角，说明 head-tail 方向可能不对。

## LEFT VIEW 的含义

`LEFT VIEW` 和 `ANTERIOR VIEW` 显示的是同一组纵向 surface，只是从左侧观察。

因此，`LEFT VIEW` 的作用不是提供另一套切片，而是补充第三维信息。一个定位在 `ANTERIOR VIEW` 中看起来正确，仍可能在前后方向偏离；这类偏差通常需要通过 `LEFT VIEW` 发现。

实际判读时，应关注：

- 蓝色轴线是否也沿亮伪影柱中心走。
- 紫色 contacts 是否在侧向视角中仍与伪影重合。
- 如果 `ANTERIOR VIEW` 对齐但 `LEFT VIEW` 偏离，说明电极在深度方向有误。
- 如果 `LEFT VIEW` 对齐但 `ANTERIOR VIEW` 偏离，说明左右方向有误。

定位时必须同时满足 `ANTERIOR VIEW` 和 `LEFT VIEW`，不能只根据其中一个视图调点。

## DORSAL VIEW 的含义

普通模式下，`DORSAL VIEW` 是以当前红点或绿点为中心，在该点所在高度取局部 axial / transverse 横断面。

可写成：

```text
P(u, v) = marker + u * [1, 0, 0] + v * [0, 1, 0]
```

其中 `marker` 是当前 head 或 tail 坐标，`u` 和 `v` 是局部窗口内的横向坐标。也就是说，普通 `DORSAL VIEW` 是单层横切面，适合检查红点或绿点是否落在该层电极伪影的中心附近。

实际判读时，应关注：

- 红色或绿色星号是否位于局部亮斑、暗斑或伪影截面的中心附近。
- 亮斑是否近似圆形或椭圆形；如果电极倾斜，横切面可能变成长椭圆。
- 不要只追最高亮度点。CT 金属伪影可能有 blooming、beam hardening 和 streak artifact，最亮点不一定是真实几何中心。
- 单层 `DORSAL VIEW` 更适合最后确认 head / tail 中心。

## X-Ray Mode 的含义

打开 X-Ray Mode 后，`DORSAL VIEW` 不再是单张横断面。它会沿当前电极轴线在 marker 附近取多层，再平滑并平均成一张投影视图。

当前本仓库代码使用对称轴向采样：

```matlab
slicstra = -10:1:10;
```

这表示围绕当前 marker 前后各取一段厚层，减少投影亮斑对某一方向的偏置。

X-Ray Mode 的作用是：

- 强化电极附近一段金属伪影的连续性。
- 更容易观察电极轴线是否穿过伪影柱。
- 帮助判断偏差是整体平移还是轴线角度错误。

X-Ray Mode 不适合直接用亮斑中心作为最终 marker 位置，因为它显示的是厚层投影，不是单层几何截面。开启 X-Ray 后看到的斜向亮带、分叉或两条伪影线，可能来自电极轴向投影和 CT streak artifact 的叠加。

## 推荐定位流程

### 1. 先用 X-Ray Mode 粗定轴线

打开 X-Ray Mode，观察 `ANTERIOR VIEW` 和 `LEFT VIEW`。

目标是让：

- 蓝色轴线沿金属伪影柱中心走。
- 紫色 contacts 沿伪影柱排列。
- 两个纵向视图都没有系统性偏离。

如果蓝线与亮柱平行但整体偏一侧，说明应整体平移 head 和 tail。  
如果一端对齐、另一端偏离，说明轴线角度不对，应固定较准的一端，调整另一端。

### 2. 用红绿点控制轴线

红点和绿点共同定义电极轴线。只移动一个点会改变轴线方向；一起移动两个点主要改变整体位置。

建议：

- 远端伪影不准时，优先调红点。
- 近端伪影不准时，优先调绿点。
- 轴线角度不准时，固定较可信的一端，微调另一端。
- 每次调整后同时回看 `ANTERIOR VIEW` 和 `LEFT VIEW`。

### 3. 关掉 X-Ray，用单层 DORSAL VIEW 精修中心

轴线大致正确后，关闭 X-Ray Mode。此时 `DORSAL VIEW` 回到单层横切面。

目标是让：

- 红星位于 distal / head 层面的局部伪影中心附近。
- 绿星位于 proximal / tail 层面的局部伪影中心附近。
- 调整后不破坏 `ANTERIOR VIEW` 和 `LEFT VIEW` 中的整体轴线对齐。

### 4. 最终复核 contacts

最后检查紫色 contacts：

- contacts 是否沿电极伪影柱排列。
- contacts 间距是否与左侧电极模型和信息框中的 spacing 一致。
- contacts 是否没有明显偏到伪影的一侧。
- 对定向电极，还需要确认 orientation / roll 相关信息是否合理。

## 判断定位较好的标准

较好的定位通常同时满足：

- `ANTERIOR VIEW` 中蓝线和紫色 contacts 位于亮伪影柱中心。
- `LEFT VIEW` 中也能看到同样的中心对齐。
- 普通 `DORSAL VIEW` 中红绿星号位于对应单层伪影中心附近。
- X-Ray Mode 下伪影柱连续，蓝线没有明显斜出伪影。
- head 和 tail 之间的距离、contacts 间距与电极型号一致。

## 常见误区

- 只看 `DORSAL VIEW` 的最亮点：最亮点可能是 CT 伪影，不一定是几何中心。
- 只看 `ANTERIOR VIEW`：可能漏掉前后方向偏差。
- 在 X-Ray Mode 下强行追椭圆中心：X-Ray Dorsal 是厚层投影，不应期待它保持单层椭圆形。
- 为了匹配局部亮斑而让整根轴线偏离：最终应以整根电极轴线和 contacts 的一致性为准。
- 忽略电极型号：不同型号的 contact 间距、contact 数量和定向结构不同，不能只凭亮斑直觉定位。

## 简短操作口诀

```text
先开 X-Ray 看轴线，
再看前视和左视是否同时居中，
关掉 X-Ray 看 Dorsal 单层中心，
最后复核 contacts 与电极型号是否一致。
```
