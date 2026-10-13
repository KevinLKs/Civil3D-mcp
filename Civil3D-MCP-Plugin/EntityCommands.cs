using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using System.Text.Json.Nodes;

namespace Civil3DMcpPlugin;

/// <summary>
/// Generic AutoCAD entity tools: read everything in an area, copy or move
/// entities, edit text and attributes, adjust line endpoints, and erase.
/// Built for template-driven drafting where existing blocks, lines, text and
/// leaders are copied and edited rather than drawn from scratch.
/// </summary>
public static class EntityCommands
{
  private const int DefaultQueryLimit = 500;
  private const int MaxQueryLimit = 5000;
  private const int MaxVerticesPerEntity = 100;

  // ---------------------------------------------------------------- query

  public static Task<object?> QueryEntitiesAsync(JsonObject? parameters)
  {
    var spaceName = PluginRuntime.GetOptionalString(parameters, "space");
    var window = ReadWindow(parameters?["window"]);
    var crossing = PluginRuntime.GetOptionalBool(parameters, "crossing") ?? true;
    var layers = ReadStringSet(parameters?["layers"]);
    var types = ReadStringSet(parameters?["types"]);
    var limit = Math.Clamp(PluginRuntime.GetOptionalInt(parameters, "limit") ?? DefaultQueryLimit, 1, MaxQueryLimit);
    var includeGeometry = PluginRuntime.GetOptionalBool(parameters, "includeGeometry") ?? true;

    return CivilExecution.ReadAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      var space = ResolveSpace(database, transaction, spaceName, OpenMode.ForRead);
      var results = new List<Dictionary<string, object?>>();
      var countsByType = new SortedDictionary<string, int>(StringComparer.OrdinalIgnoreCase);
      var matched = 0;

      foreach (ObjectId id in space.Record)
      {
        if (transaction.GetObject(id, OpenMode.ForRead, false) is not Entity entity)
        {
          continue;
        }

        if (!MatchesFilters(entity, window, crossing, layers, types))
        {
          continue;
        }

        matched++;
        var typeName = TypeName(entity);
        countsByType[typeName] = countsByType.TryGetValue(typeName, out var count) ? count + 1 : 1;

        if (results.Count < limit)
        {
          results.Add(Describe(entity, transaction, includeGeometry));
        }
      }

      return new Dictionary<string, object?>
      {
        ["space"] = space.Name,
        ["layouts"] = ListLayoutNames(database, transaction),
        ["matched"] = matched,
        ["returned"] = results.Count,
        ["truncated"] = matched > results.Count,
        ["countsByType"] = countsByType,
        ["entities"] = results,
      };
    });
  }

  // ----------------------------------------------------------- copy / move

  public static Task<object?> CopyEntitiesAsync(JsonObject? parameters)
  {
    if (PluginRuntime.GetParameter(parameters, "operations") is not JsonArray operations || operations.Count == 0)
    {
      throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "copyEntities requires a non-empty operations array.");
    }

    return CivilExecution.WriteAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      var results = new List<Dictionary<string, object?>>();

      for (var index = 0; index < operations.Count; index++)
      {
        if (operations[index] is not JsonObject operation)
        {
          throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Operation {index} must be an object.");
        }

        var mode = (operation["mode"]?.GetValue<string>() ?? "copy").Trim().ToLowerInvariant();
        if (mode != "copy" && mode != "move")
        {
          throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Operation {index}: mode must be 'copy' or 'move'.");
        }

        var dx = operation["dx"]?.GetValue<double>() ?? 0.0;
        var dy = operation["dy"]?.GetValue<double>() ?? 0.0;
        var sourceSpaceName = operation["space"]?.GetValue<string>();
        var targetSpaceName = operation["targetSpace"]?.GetValue<string>();

        var sourceSpace = ResolveSpace(database, transaction, sourceSpaceName, OpenMode.ForRead);
        var ids = SelectIds(database, transaction, sourceSpace, operation, index);
        if (ids.Count == 0)
        {
          throw new JsonRpcDispatchException("CIVIL3D.NOT_FOUND", $"Operation {index} selected no entities.");
        }

        var displacement = Matrix3d.Displacement(new Vector3d(dx, dy, 0));
        var mirrorX = operation["mirrorX"]?.GetValue<double>();
        var handleMap = new Dictionary<string, string>();

        if (mode == "move")
        {
          if (!string.IsNullOrWhiteSpace(targetSpaceName))
          {
            throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Operation {index}: targetSpace is only supported for copy.");
          }

          foreach (ObjectId id in ids)
          {
            var entity = (Entity)transaction.GetObject(id, OpenMode.ForWrite);
            entity.TransformBy(displacement);
            if (mirrorX is { } mx)
            {
              MirrorReadable(entity, mx, transaction);
            }
            var handle = CivilObjectUtils.GetHandle(entity);
            handleMap[handle] = handle;
          }
        }
        else
        {
          var targetSpace = string.IsNullOrWhiteSpace(targetSpaceName)
            ? sourceSpace
            : ResolveSpace(database, transaction, targetSpaceName, OpenMode.ForRead);

          var mapping = new IdMapping();
          database.DeepCloneObjects(ids, targetSpace.Record.ObjectId, mapping, false);

          foreach (IdPair pair in mapping)
          {
            if (!pair.IsPrimary || !pair.IsCloned || !ids.Contains(pair.Key))
            {
              continue;
            }

            var clone = (Entity)transaction.GetObject(pair.Value, OpenMode.ForWrite);
            clone.TransformBy(displacement);
            if (mirrorX is { } mx)
            {
              MirrorReadable(clone, mx, transaction);
            }
            handleMap[pair.Key.Handle.ToString()] = clone.Handle.ToString();
          }
        }

        results.Add(new Dictionary<string, object?>
        {
          ["index"] = index,
          ["mode"] = mode,
          ["count"] = handleMap.Count,
          ["dx"] = dx,
          ["dy"] = dy,
          ["mirrorX"] = mirrorX,
          ["handles"] = handleMap,
        });
      }

      return new Dictionary<string, object?>
      {
        ["operations"] = results,
      };
    });
  }

  // ------------------------------------------------------------------ edit

  public static Task<object?> EditEntitiesAsync(JsonObject? parameters)
  {
    if (PluginRuntime.GetParameter(parameters, "edits") is not JsonArray edits || edits.Count == 0)
    {
      throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "editEntities requires a non-empty edits array.");
    }

    return CivilExecution.WriteAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      var results = new List<Dictionary<string, object?>>();

      for (var index = 0; index < edits.Count; index++)
      {
        if (edits[index] is not JsonObject edit)
        {
          throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index} must be an object.");
        }

        var handle = edit["handle"]?.GetValue<string>()
          ?? throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index} is missing handle.");
        var entity = (Entity)transaction.GetObject(GetIdFromHandle(database, handle), OpenMode.ForWrite);
        var changed = new List<string>();

        var text = edit["text"]?.GetValue<string>();
        if (text != null)
        {
          SetText(entity, text, transaction, index);
          changed.Add("text");
        }

        if (edit["attributes"] is JsonObject attributes && attributes.Count > 0)
        {
          if (entity is not BlockReference blockRef)
          {
            throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index}: attributes can only be set on block references.");
          }

          var missing = SetAttributes(blockRef, attributes, transaction);
          if (missing.Count > 0)
          {
            throw new JsonRpcDispatchException("CIVIL3D.NOT_FOUND", $"Edit {index}: attribute tags not found: {string.Join(", ", missing)}.");
          }

          changed.Add("attributes");
        }

        var start = ReadPoint(edit["start"]);
        var end = ReadPoint(edit["end"]);
        if (start != null || end != null)
        {
          if (entity is not Line line)
          {
            throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index}: start/end can only be set on lines.");
          }

          if (start is { } s)
          {
            line.StartPoint = new Point3d(s.X, s.Y, line.StartPoint.Z);
            changed.Add("start");
          }

          if (end is { } e)
          {
            line.EndPoint = new Point3d(e.X, e.Y, line.EndPoint.Z);
            changed.Add("end");
          }
        }

        var xLine1 = ReadPoint(edit["xLine1"]);
        var xLine2 = ReadPoint(edit["xLine2"]);
        var dimLine = ReadPoint(edit["dimLine"]);
        if (xLine1 != null || xLine2 != null || dimLine != null)
        {
          SetDimensionPoints(entity, xLine1, xLine2, dimLine, index);
          changed.Add("dimensionPoints");
        }

        if (edit["vertices"] is JsonArray vertexNodes)
        {
          var vertices = vertexNodes.Select(node => ReadPoint(node)
            ?? throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index}: every vertex needs x and y.")).ToList();
          SetVertices(entity, vertices, index);
          changed.Add("vertices");
        }

        var colorIndex = edit["colorIndex"]?.GetValue<int>();
        if (colorIndex != null)
        {
          if (colorIndex < 0 || colorIndex > 256)
          {
            throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index}: colorIndex must be 0-256 (0 = ByBlock, 256 = ByLayer).");
          }

          entity.ColorIndex = colorIndex.Value;
          changed.Add("colorIndex");
        }

        var linetype = edit["linetype"]?.GetValue<string>();
        if (!string.IsNullOrWhiteSpace(linetype))
        {
          entity.LinetypeId = GetLinetypeId(database, transaction, linetype, index);
          changed.Add("linetype");
        }

        var layer = edit["layer"]?.GetValue<string>();
        if (!string.IsNullOrWhiteSpace(layer))
        {
          entity.LayerId = LookupUtils.GetLayerId(database, transaction, layer);
          changed.Add("layer");
        }

        if (changed.Count == 0)
        {
          throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index} has nothing to change.");
        }

        results.Add(new Dictionary<string, object?>
        {
          ["index"] = index,
          ["handle"] = handle,
          ["type"] = TypeName(entity),
          ["changed"] = changed,
        });
      }

      return new Dictionary<string, object?>
      {
        ["edits"] = results,
      };
    });
  }

  // ----------------------------------------------------------------- erase

  public static Task<object?> EraseEntitiesAsync(JsonObject? parameters)
  {
    var handles = ReadStringList(PluginRuntime.GetParameter(parameters, "handles") as JsonNode);
    if (handles.Count == 0)
    {
      throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "eraseEntities requires a non-empty handles array.");
    }

    return CivilExecution.WriteAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      var erased = new List<string>();
      foreach (var handle in handles)
      {
        var entity = (Entity)transaction.GetObject(GetIdFromHandle(database, handle), OpenMode.ForWrite);
        entity.Erase();
        erased.Add(handle);
      }

      return new Dictionary<string, object?>
      {
        ["erased"] = erased,
        ["count"] = erased.Count,
      };
    });
  }

  // --------------------------------------------------------------- helpers

  private sealed record SpaceInfo(string Name, BlockTableRecord Record);

  private readonly record struct Window(double MinX, double MinY, double MaxX, double MaxY);

  private static SpaceInfo ResolveSpace(Database database, Transaction transaction, string? spaceName, OpenMode openMode)
  {
    if (string.IsNullOrWhiteSpace(spaceName) || spaceName.Equals("model", StringComparison.OrdinalIgnoreCase))
    {
      var blockTable = (BlockTable)transaction.GetObject(database.BlockTableId, OpenMode.ForRead);
      var record = (BlockTableRecord)transaction.GetObject(blockTable[BlockTableRecord.ModelSpace], openMode);
      return new SpaceInfo("Model", record);
    }

    var layouts = (DBDictionary)transaction.GetObject(database.LayoutDictionaryId, OpenMode.ForRead);
    foreach (DBDictionaryEntry entry in layouts)
    {
      if (!entry.Key.Equals(spaceName, StringComparison.OrdinalIgnoreCase))
      {
        continue;
      }

      var layout = (Layout)transaction.GetObject(entry.Value, OpenMode.ForRead);
      var record = (BlockTableRecord)transaction.GetObject(layout.BlockTableRecordId, openMode);
      return new SpaceInfo(layout.LayoutName, record);
    }

    throw new JsonRpcDispatchException(
      "CIVIL3D.NOT_FOUND",
      $"Space '{spaceName}' not found. Use 'model' or one of: {string.Join(", ", ListLayoutNames(database, transaction))}.");
  }

  private static List<string> ListLayoutNames(Database database, Transaction transaction)
  {
    var names = new List<(int Order, string Name)>();
    var layouts = (DBDictionary)transaction.GetObject(database.LayoutDictionaryId, OpenMode.ForRead);
    foreach (DBDictionaryEntry entry in layouts)
    {
      var layout = (Layout)transaction.GetObject(entry.Value, OpenMode.ForRead);
      names.Add((layout.TabOrder, layout.LayoutName));
    }

    return names.OrderBy(n => n.Order).Select(n => n.Name).ToList();
  }

  private static ObjectIdCollection SelectIds(Database database, Transaction transaction, SpaceInfo space, JsonObject operation, int index)
  {
    var ids = new ObjectIdCollection();
    var handles = ReadStringList(operation["handles"]);
    var window = ReadWindow(operation["window"]);

    if (handles.Count == 0 && window == null)
    {
      throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Operation {index} needs handles or a window.");
    }

    foreach (var handle in handles)
    {
      var id = GetIdFromHandle(database, handle);
      if (!ids.Contains(id))
      {
        ids.Add(id);
      }
    }

    if (window != null)
    {
      var crossing = operation["crossing"]?.GetValue<bool>() ?? false;
      var layers = ReadStringSet(operation["layers"]);
      var types = ReadStringSet(operation["types"]);
      foreach (ObjectId id in space.Record)
      {
        if (ids.Contains(id))
        {
          continue;
        }

        if (transaction.GetObject(id, OpenMode.ForRead, false) is Entity entity &&
            MatchesFilters(entity, window, crossing, layers, types))
        {
          ids.Add(id);
        }
      }
    }

    return ids;
  }

  private static bool MatchesFilters(Entity entity, Window? window, bool crossing, HashSet<string>? layers, HashSet<string>? types)
  {
    if (layers != null && !layers.Contains(entity.Layer))
    {
      return false;
    }

    if (types != null && !types.Contains(TypeName(entity)))
    {
      return false;
    }

    if (window is not { } w)
    {
      return true;
    }

    var extents = TryGetExtents(entity);
    if (extents is not { } e)
    {
      return false;
    }

    if (crossing)
    {
      return e.MaxPoint.X >= w.MinX && e.MinPoint.X <= w.MaxX &&
             e.MaxPoint.Y >= w.MinY && e.MinPoint.Y <= w.MaxY;
    }

    return e.MinPoint.X >= w.MinX && e.MaxPoint.X <= w.MaxX &&
           e.MinPoint.Y >= w.MinY && e.MaxPoint.Y <= w.MaxY;
  }

  private static Extents3d? TryGetExtents(Entity entity)
  {
    try
    {
      return entity.GeometricExtents;
    }
    catch
    {
      return null;
    }
  }

  private static ObjectId GetIdFromHandle(Database database, string handle)
  {
    long value;
    try
    {
      value = Convert.ToInt64(handle.Trim(), 16);
    }
    catch (Exception)
    {
      throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"'{handle}' is not a valid hexadecimal handle.");
    }

    if (!database.TryGetObjectId(new Handle(value), out var id) || id.IsNull || id.IsErased)
    {
      throw new JsonRpcDispatchException("CIVIL3D.NOT_FOUND", $"No entity found for handle '{handle}'.");
    }

    return id;
  }

  private static string TypeName(Entity entity)
  {
    try
    {
      var dxf = entity.GetRXClass().DxfName;
      if (!string.IsNullOrWhiteSpace(dxf))
      {
        return dxf;
      }
    }
    catch
    {
      // fall through to the managed type name
    }

    return entity.GetType().Name;
  }

  private static Dictionary<string, object?> Describe(Entity entity, Transaction transaction, bool includeGeometry)
  {
    var info = new Dictionary<string, object?>
    {
      ["handle"] = CivilObjectUtils.GetHandle(entity),
      ["type"] = TypeName(entity),
      ["layer"] = entity.Layer,
    };

    if (entity.ColorIndex != 256)
    {
      info["colorIndex"] = entity.ColorIndex;
    }

    if (!string.Equals(entity.Linetype, "BYLAYER", StringComparison.OrdinalIgnoreCase))
    {
      info["linetype"] = entity.Linetype;
    }

    if (TryGetExtents(entity) is { } extents)
    {
      info["extents"] = new Dictionary<string, object?>
      {
        ["min"] = P(extents.MinPoint),
        ["max"] = P(extents.MaxPoint),
      };
    }

    switch (entity)
    {
      case Line line:
        if (includeGeometry)
        {
          info["start"] = P(line.StartPoint);
          info["end"] = P(line.EndPoint);
          info["length"] = R(line.Length);
        }
        break;

      case Polyline polyline:
        info["closed"] = polyline.Closed;
        info["vertexCount"] = polyline.NumberOfVertices;
        if (includeGeometry)
        {
          var vertices = new List<object>();
          for (var i = 0; i < Math.Min(polyline.NumberOfVertices, MaxVerticesPerEntity); i++)
          {
            vertices.Add(P(polyline.GetPoint2dAt(i)));
          }
          info["vertices"] = vertices;
        }
        break;

      case Circle circle:
        info["center"] = P(circle.Center);
        info["radius"] = R(circle.Radius);
        break;

      case Arc arc:
        info["center"] = P(arc.Center);
        info["radius"] = R(arc.Radius);
        info["startAngleDeg"] = R(arc.StartAngle * 180.0 / Math.PI);
        info["endAngleDeg"] = R(arc.EndAngle * 180.0 / Math.PI);
        break;

      case DBText text:
        info["text"] = text.TextString;
        info["position"] = P(text.Position);
        info["height"] = R(text.Height);
        info["rotationDeg"] = R(text.Rotation * 180.0 / Math.PI);
        info["style"] = text.TextStyleName;
        break;

      case MText mtext:
        info["text"] = mtext.Text;
        info["contents"] = mtext.Contents;
        info["location"] = P(mtext.Location);
        info["height"] = R(mtext.TextHeight);
        info["width"] = R(mtext.Width);
        info["rotationDeg"] = R(mtext.Rotation * 180.0 / Math.PI);
        info["style"] = mtext.TextStyleName;
        break;

      case MLeader mleader:
        DescribeMLeader(mleader, info, includeGeometry);
        break;

      case Leader leader:
        if (includeGeometry)
        {
          var vertices = new List<object>();
          for (var i = 0; i < Math.Min(leader.NumVertices, MaxVerticesPerEntity); i++)
          {
            vertices.Add(P(leader.VertexAt(i)));
          }
          info["vertices"] = vertices;
        }
        if (!leader.Annotation.IsNull)
        {
          info["annotationHandle"] = leader.Annotation.Handle.ToString();
        }
        break;

      case Dimension dimension:
        info["measurement"] = R(dimension.Measurement);
        info["dimensionText"] = dimension.DimensionText;
        if (includeGeometry && dimension is RotatedDimension rd)
        {
          info["xLine1"] = P(rd.XLine1Point);
          info["xLine2"] = P(rd.XLine2Point);
          info["dimLine"] = P(rd.DimLinePoint);
          info["rotationDeg"] = R(rd.Rotation * 180.0 / Math.PI);
        }
        else if (includeGeometry && dimension is AlignedDimension ad)
        {
          info["xLine1"] = P(ad.XLine1Point);
          info["xLine2"] = P(ad.XLine2Point);
          info["dimLine"] = P(ad.DimLinePoint);
        }
        break;

      case BlockReference blockRef:
        DescribeBlockReference(blockRef, transaction, info);
        break;
    }

    return info;
  }

  private static void DescribeBlockReference(BlockReference blockRef, Transaction transaction, Dictionary<string, object?> info)
  {
    var name = blockRef.Name;
    try
    {
      if (blockRef.IsDynamicBlock)
      {
        var dynamicRecord = (BlockTableRecord)transaction.GetObject(blockRef.DynamicBlockTableRecord, OpenMode.ForRead);
        info["anonymousName"] = name;
        name = dynamicRecord.Name;
        info["dynamic"] = true;
      }
    }
    catch
    {
      // keep the plain block name
    }

    info["blockName"] = name;
    info["position"] = P(blockRef.Position);
    info["rotationDeg"] = R(blockRef.Rotation * 180.0 / Math.PI);

    var scale = blockRef.ScaleFactors;
    if (Math.Abs(scale.X - 1) > 1e-9 || Math.Abs(scale.Y - 1) > 1e-9 || Math.Abs(scale.Z - 1) > 1e-9)
    {
      info["scale"] = new Dictionary<string, object?> { ["x"] = R(scale.X), ["y"] = R(scale.Y), ["z"] = R(scale.Z) };
    }

    var attributes = new Dictionary<string, object?>();
    foreach (ObjectId attributeId in blockRef.AttributeCollection)
    {
      if (transaction.GetObject(attributeId, OpenMode.ForRead, false) is AttributeReference attribute)
      {
        attributes[attribute.Tag] = attribute.IsMTextAttribute ? attribute.MTextAttribute.Text : attribute.TextString;
      }
    }

    if (attributes.Count > 0)
    {
      info["attributes"] = attributes;
    }
  }

  private static void DescribeMLeader(MLeader mleader, Dictionary<string, object?> info, bool includeGeometry)
  {
    try
    {
      if (mleader.ContentType == ContentType.MTextContent && mleader.MText is { } mtext)
      {
        info["text"] = mtext.Text;
        info["contents"] = mtext.Contents;
        info["textLocation"] = P(mtext.Location);
      }
      else if (mleader.ContentType == ContentType.BlockContent)
      {
        info["contentBlock"] = true;
      }
    }
    catch
    {
      // content not readable; leave it out
    }

    if (!includeGeometry)
    {
      return;
    }

    try
    {
      var lines = new List<object>();
      foreach (int leaderIndex in mleader.GetLeaderIndexes())
      {
        foreach (int lineIndex in mleader.GetLeaderLineIndexes(leaderIndex))
        {
          var vertices = new List<object>();
          var count = mleader.VerticesCount(lineIndex);
          for (var i = 0; i < Math.Min(count, MaxVerticesPerEntity); i++)
          {
            vertices.Add(P(mleader.GetVertex(lineIndex, i)));
          }
          lines.Add(vertices);
        }
      }

      if (lines.Count > 0)
      {
        info["leaderLines"] = lines;
      }
    }
    catch
    {
      // leader geometry not readable; leave it out
    }
  }

  private static void SetText(Entity entity, string text, Transaction transaction, int index)
  {
    switch (entity)
    {
      case AttributeReference attribute:
        if (attribute.IsMTextAttribute)
        {
          var mtextAttribute = attribute.MTextAttribute;
          mtextAttribute.Contents = text;
          attribute.MTextAttribute = mtextAttribute;
          attribute.UpdateMTextAttribute();
        }
        else
        {
          attribute.TextString = text;
        }
        break;

      case DBText dbText:
        dbText.TextString = text;
        break;

      case MText mtext:
        mtext.Contents = text;
        break;

      case MLeader mleader:
        if (mleader.ContentType != ContentType.MTextContent || mleader.MText == null)
        {
          throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index}: this multileader has no text content.");
        }

        var content = mleader.MText;
        content.Contents = text;
        mleader.MText = content;
        break;

      case Dimension dimension:
        dimension.DimensionText = text;
        break;

      default:
        throw new JsonRpcDispatchException(
          "CIVIL3D.INVALID_INPUT",
          $"Edit {index}: text cannot be set on a {TypeName(entity)}. Use attributes for block references.");
    }
  }

  private static List<string> SetAttributes(BlockReference blockRef, JsonObject values, Transaction transaction)
  {
    var pending = values
      .Where(pair => pair.Value != null)
      .ToDictionary(pair => pair.Key, pair => pair.Value!.GetValue<string>(), StringComparer.OrdinalIgnoreCase);

    foreach (ObjectId attributeId in blockRef.AttributeCollection)
    {
      if (transaction.GetObject(attributeId, OpenMode.ForWrite, false) is not AttributeReference attribute)
      {
        continue;
      }

      if (!pending.TryGetValue(attribute.Tag, out var value))
      {
        continue;
      }

      if (attribute.IsMTextAttribute)
      {
        var mtext = attribute.MTextAttribute;
        mtext.Contents = value;
        attribute.MTextAttribute = mtext;
        attribute.UpdateMTextAttribute();
      }
      else
      {
        attribute.TextString = value;
      }

      pending.Remove(attribute.Tag);
    }

    return pending.Keys.ToList();
  }

  /// <summary>
  /// Mirrors an entity across the vertical line x = mirrorX while keeping text
  /// readable (like MIRROR with MIRRTEXT = 0): text anchors are mirrored and
  /// left/right justification is swapped instead of reversing the characters.
  /// </summary>
  private static void MirrorReadable(Entity entity, double mirrorX, Transaction transaction)
  {
    var mirror = Matrix3d.Mirroring(new Line3d(new Point3d(mirrorX, 0, 0), new Point3d(mirrorX, 1, 0)));
    Point3d Mir(Point3d p) => new(2 * mirrorX - p.X, p.Y, p.Z);

    switch (entity)
    {
      case AttributeReference:
        // Owned by a block reference; handled with its block.
        return;

      case DBText text:
        var textState = TextState.Capture(text);
        textState.Apply(text, Mir);
        return;

      case MText mtext:
        mtext.Location = Mir(mtext.Location);
        mtext.Rotation = -mtext.Rotation;
        mtext.Attachment = SwapAttachment(mtext.Attachment);
        return;

      case BlockReference blockRef:
        var attributeStates = new List<(AttributeReference Attribute, TextState State)>();
        foreach (ObjectId attributeId in blockRef.AttributeCollection)
        {
          if (transaction.GetObject(attributeId, OpenMode.ForWrite, false) is AttributeReference attribute && !attribute.IsMTextAttribute)
          {
            attributeStates.Add((attribute, TextState.Capture(attribute)));
          }
        }

        blockRef.TransformBy(mirror);
        foreach (var (attribute, state) in attributeStates)
        {
          attribute.IsMirroredInX = false;
          attribute.IsMirroredInY = false;
          state.Apply(attribute, Mir);
        }
        return;

      case RotatedDimension rotated:
        rotated.XLine1Point = Mir(rotated.XLine1Point);
        rotated.XLine2Point = Mir(rotated.XLine2Point);
        rotated.DimLinePoint = Mir(rotated.DimLinePoint);
        rotated.Rotation = Math.PI - rotated.Rotation;
        if (!rotated.UsingDefaultTextPosition)
        {
          rotated.TextPosition = Mir(rotated.TextPosition);
        }
        rotated.RecomputeDimensionBlock(true);
        return;

      case AlignedDimension aligned:
        aligned.XLine1Point = Mir(aligned.XLine1Point);
        aligned.XLine2Point = Mir(aligned.XLine2Point);
        aligned.DimLinePoint = Mir(aligned.DimLinePoint);
        if (!aligned.UsingDefaultTextPosition)
        {
          aligned.TextPosition = Mir(aligned.TextPosition);
        }
        aligned.RecomputeDimensionBlock(true);
        return;

      case Dimension dimension:
        dimension.TransformBy(mirror);
        dimension.RecomputeDimensionBlock(true);
        return;

      default:
        entity.TransformBy(mirror);
        return;
    }
  }

  private sealed record TextState(Point3d Anchor, TextHorizontalMode Horizontal, TextVerticalMode Vertical, double Rotation)
  {
    public static TextState Capture(DBText text)
    {
      var usesPosition = text.HorizontalMode == TextHorizontalMode.TextLeft && text.VerticalMode == TextVerticalMode.TextBase;
      return new TextState(usesPosition ? text.Position : text.AlignmentPoint, text.HorizontalMode, text.VerticalMode, text.Rotation);
    }

    public void Apply(DBText text, Func<Point3d, Point3d> mirrorPoint)
    {
      var horizontal = Horizontal switch
      {
        TextHorizontalMode.TextLeft => TextHorizontalMode.TextRight,
        TextHorizontalMode.TextRight => TextHorizontalMode.TextLeft,
        _ => Horizontal,
      };

      var anchor = mirrorPoint(Anchor);
      text.IsMirroredInX = false;
      text.IsMirroredInY = false;
      text.Rotation = -Rotation;
      text.HorizontalMode = horizontal;
      text.VerticalMode = Vertical;

      if (horizontal == TextHorizontalMode.TextLeft && Vertical == TextVerticalMode.TextBase)
      {
        text.Position = anchor;
      }
      else
      {
        text.AlignmentPoint = anchor;
      }

      text.AdjustAlignment(text.Database);
    }
  }

  private static AttachmentPoint SwapAttachment(AttachmentPoint attachment) => attachment switch
  {
    AttachmentPoint.TopLeft => AttachmentPoint.TopRight,
    AttachmentPoint.TopRight => AttachmentPoint.TopLeft,
    AttachmentPoint.MiddleLeft => AttachmentPoint.MiddleRight,
    AttachmentPoint.MiddleRight => AttachmentPoint.MiddleLeft,
    AttachmentPoint.BottomLeft => AttachmentPoint.BottomRight,
    AttachmentPoint.BottomRight => AttachmentPoint.BottomLeft,
    _ => attachment,
  };

  private static void SetVertices(Entity entity, List<Point2d> vertices, int index)
  {
    if (vertices.Count < 2)
    {
      throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index}: vertices needs at least two points.");
    }

    switch (entity)
    {
      case Polyline polyline:
        for (var i = 0; i < vertices.Count; i++)
        {
          if (i < polyline.NumberOfVertices)
          {
            polyline.SetPointAt(i, vertices[i]);
          }
          else
          {
            polyline.AddVertexAt(i, vertices[i], 0, 0, 0);
          }
        }

        while (polyline.NumberOfVertices > vertices.Count)
        {
          polyline.RemoveVertexAt(polyline.NumberOfVertices - 1);
        }
        break;

      case Leader leader:
        var z = leader.NumVertices > 0 ? leader.VertexAt(0).Z : 0;
        for (var i = 0; i < vertices.Count; i++)
        {
          var point = new Point3d(vertices[i].X, vertices[i].Y, z);
          if (i < leader.NumVertices)
          {
            leader.SetVertexAt(i, point);
          }
          else
          {
            leader.AppendVertex(point);
          }
        }

        while (leader.NumVertices > vertices.Count)
        {
          leader.RemoveLastVertex();
        }
        break;

      case Line line:
        if (vertices.Count != 2)
        {
          throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index}: a line takes exactly two vertices.");
        }

        line.StartPoint = new Point3d(vertices[0].X, vertices[0].Y, line.StartPoint.Z);
        line.EndPoint = new Point3d(vertices[1].X, vertices[1].Y, line.EndPoint.Z);
        break;

      default:
        throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index}: vertices can be set on lines, polylines and leaders, not {TypeName(entity)}.");
    }
  }

  private static void SetDimensionPoints(Entity entity, Point2d? xLine1, Point2d? xLine2, Point2d? dimLine, int index)
  {
    static Point3d To3d(Point2d p, Point3d current) => new(p.X, p.Y, current.Z);

    switch (entity)
    {
      case RotatedDimension rotated:
        if (xLine1 is { } a) rotated.XLine1Point = To3d(a, rotated.XLine1Point);
        if (xLine2 is { } b) rotated.XLine2Point = To3d(b, rotated.XLine2Point);
        if (dimLine is { } c) rotated.DimLinePoint = To3d(c, rotated.DimLinePoint);
        rotated.RecomputeDimensionBlock(true);
        break;

      case AlignedDimension aligned:
        if (xLine1 is { } d) aligned.XLine1Point = To3d(d, aligned.XLine1Point);
        if (xLine2 is { } e) aligned.XLine2Point = To3d(e, aligned.XLine2Point);
        if (dimLine is { } f) aligned.DimLinePoint = To3d(f, aligned.DimLinePoint);
        aligned.RecomputeDimensionBlock(true);
        break;

      default:
        throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Edit {index}: xLine1/xLine2/dimLine can only be set on linear (rotated or aligned) dimensions, not {TypeName(entity)}.");
    }
  }

  private static ObjectId GetLinetypeId(Database database, Transaction transaction, string name, int index)
  {
    var linetypes = (LinetypeTable)transaction.GetObject(database.LinetypeTableId, OpenMode.ForRead);
    if (linetypes.Has(name))
    {
      return linetypes[name];
    }

    throw new JsonRpcDispatchException("CIVIL3D.NOT_FOUND", $"Edit {index}: linetype '{name}' is not loaded in this drawing.");
  }

  private static Window? ReadWindow(JsonNode? node)
  {
    if (node is not JsonObject window)
    {
      return null;
    }

    var minX = window["minX"]?.GetValue<double>();
    var minY = window["minY"]?.GetValue<double>();
    var maxX = window["maxX"]?.GetValue<double>();
    var maxY = window["maxY"]?.GetValue<double>();
    if (minX == null || minY == null || maxX == null || maxY == null)
    {
      throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "window requires minX, minY, maxX and maxY.");
    }

    return new Window(
      Math.Min(minX.Value, maxX.Value),
      Math.Min(minY.Value, maxY.Value),
      Math.Max(minX.Value, maxX.Value),
      Math.Max(minY.Value, maxY.Value));
  }

  private static Point2d? ReadPoint(JsonNode? node)
  {
    if (node is not JsonObject point)
    {
      return null;
    }

    var x = point["x"]?.GetValue<double>() ?? throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "Point is missing x.");
    var y = point["y"]?.GetValue<double>() ?? throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "Point is missing y.");
    return new Point2d(x, y);
  }

  private static List<string> ReadStringList(JsonNode? node)
  {
    var list = new List<string>();
    if (node is JsonArray array)
    {
      foreach (var item in array)
      {
        var value = item?.GetValue<string>();
        if (!string.IsNullOrWhiteSpace(value))
        {
          list.Add(value.Trim());
        }
      }
    }

    return list;
  }

  private static HashSet<string>? ReadStringSet(JsonNode? node)
  {
    var list = ReadStringList(node);
    return list.Count == 0 ? null : new HashSet<string>(list, StringComparer.OrdinalIgnoreCase);
  }

  private static double R(double value) => Math.Round(value, 4);

  private static Dictionary<string, object?> P(Point3d point) => new() { ["x"] = R(point.X), ["y"] = R(point.Y) };

  private static Dictionary<string, object?> P(Point2d point) => new() { ["x"] = R(point.X), ["y"] = R(point.Y) };
}
