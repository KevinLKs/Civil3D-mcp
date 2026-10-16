using System.Text.Json.Nodes;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;

namespace Civil3DMcpPlugin;

public static class PointCommands
{
  public static Task<object?> ListCogoPointsAsync(JsonObject? parameters)
  {
    var groupName = PluginRuntime.GetOptionalString(parameters, "groupName");
    var limit = PluginRuntime.GetOptionalInt(parameters, "limit") ?? int.MaxValue;
    var offset = PluginRuntime.GetOptionalInt(parameters, "offset") ?? 0;
    var includeRanges = ParseNumberRanges(PluginRuntime.GetOptionalString(parameters, "includeNumbers"));
    var excludeRanges = ParseNumberRanges(PluginRuntime.GetOptionalString(parameters, "excludeNumbers"));
    var descriptionPatterns = ParseWildcardPatterns(PluginRuntime.GetOptionalString(parameters, "includeDescriptions"));
    var layerSet = ParseLayerSet(PluginRuntime.GetParameter(parameters, "layers") as JsonArray);
    var window = ParseWindow(PluginRuntime.GetParameter(parameters, "window") as JsonObject);

    return CivilExecution.ReadAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      HashSet<uint>? allowedNumbers = null;
      if (!string.IsNullOrWhiteSpace(groupName))
      {
        allowedNumbers = TryGetPointNumbersForGroup(civilDoc, transaction, groupName!);
      }

      var allPoints = EnumeratePoints(civilDoc, transaction)
        .Where(p => allowedNumbers == null || allowedNumbers.Contains(p.PointNumber))
        .Where(p => includeRanges == null || InRanges(includeRanges, p.PointNumber))
        .Where(p => excludeRanges == null || !InRanges(excludeRanges, p.PointNumber))
        .Where(p => descriptionPatterns == null || descriptionPatterns.Any(rx => rx.IsMatch(p.RawDescription ?? string.Empty)))
        .Where(p => layerSet == null || layerSet.Contains(p.Layer))
        .Where(p => window == null || (p.Location.X >= window.Value.minX && p.Location.X <= window.Value.maxX && p.Location.Y >= window.Value.minY && p.Location.Y <= window.Value.maxY))
        .OrderBy(p => p.PointNumber)
        .ToList();

      var page = allPoints.Skip(offset).Take(limit).Select(CivilObjectUtils.ToPointData).ToList();

      return new Dictionary<string, object?>
      {
        ["totalCount"] = allPoints.Count,
        ["returnedCount"] = page.Count,
        ["points"] = page,
        ["units"] = CivilObjectUtils.LinearUnits(database),
      };
    });
  }

  public static Task<object?> GetCogoPointAsync(JsonObject? parameters)
  {
    var pointNumber = (uint)PluginRuntime.GetRequiredInt(parameters, "pointNumber");
    return CivilExecution.ReadAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      var point = FindPointByNumber(civilDoc, transaction, pointNumber, Autodesk.AutoCAD.DatabaseServices.OpenMode.ForRead);
      return CivilObjectUtils.ToPointData(point);
    });
  }

  public static Task<object?> CreateCogoPointsAsync(JsonObject? parameters)
  {
    var pointsNode = PluginRuntime.GetParameter(parameters, "points") as JsonArray;
    if (pointsNode == null || pointsNode.Count == 0)
    {
      throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "createCogoPoints requires a non-empty 'points' array.");
    }

    var startNumber = PluginRuntime.GetOptionalInt(parameters, "startNumber");

    return CivilExecution.WriteAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      var createdNumbers = new List<uint>();
      var collection = civilDoc.CogoPoints;

      for (var index = 0; index < pointsNode.Count; index++)
      {
        if (pointsNode[index] is not JsonObject pointNode)
        {
          continue;
        }

        var x = pointNode["x"]?.GetValue<double>() ?? throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "Point is missing x.");
        var y = pointNode["y"]?.GetValue<double>() ?? throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "Point is missing y.");
        var z = pointNode["z"]?.GetValue<double>() ?? throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "Point is missing z.");
        var description = pointNode["description"]?.GetValue<string?>() ?? string.Empty;

        var objectId = collection.Add(new Point3d(x, y, z), description, true);
        var point = CivilObjectUtils.GetRequiredObject<CogoPoint>(transaction, objectId, Autodesk.AutoCAD.DatabaseServices.OpenMode.ForWrite);

        if (startNumber.HasValue)
        {
          point.PointNumber = (uint)(startNumber.Value + index);
        }

        createdNumbers.Add(point.PointNumber);
      }

      return new Dictionary<string, object?>
      {
        ["created"] = createdNumbers.Count,
        ["pointNumbers"] = createdNumbers,
      };
    });
  }

  public static Task<object?> ImportCogoPointsAsync(JsonObject? parameters)
  {
    var format = PluginRuntime.GetRequiredString(parameters, "format");
    var data = PluginRuntime.GetRequiredString(parameters, "data");
    var targetSurface = PluginRuntime.GetOptionalString(parameters, "targetSurface");
    if (!string.IsNullOrWhiteSpace(targetSurface))
    {
      throw new JsonRpcDispatchException(
        "CIVIL3D.API_ERROR",
        "Importing COGO points directly into a target surface is not implemented. No points were imported.");
    }

    return CivilExecution.WriteAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      var createdNumbers = new List<uint>();
      foreach (var parsed in ParsePointImport(data, format))
      {
        var objectId = civilDoc.CogoPoints.Add(new Point3d(parsed.X, parsed.Y, parsed.Z), parsed.Description, true);
        var point = CivilObjectUtils.GetRequiredObject<CogoPoint>(transaction, objectId, Autodesk.AutoCAD.DatabaseServices.OpenMode.ForRead);
        createdNumbers.Add(point.PointNumber);
      }

      return new Dictionary<string, object?>
      {
        ["imported"] = createdNumbers.Count,
        ["pointNumbers"] = createdNumbers,
        ["targetSurface"] = null,
      };
    });
  }

  public static Task<object?> DeleteCogoPointsAsync(JsonObject? parameters)
  {
    var numbersNode = PluginRuntime.GetParameter(parameters, "pointNumbers") as JsonArray;
    if (numbersNode == null || numbersNode.Count == 0)
    {
      throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", "deleteCogoPoints requires 'pointNumbers'.");
    }

    var pointNumbers = numbersNode.Select(node => (uint)(node?.GetValue<int>() ?? 0)).Where(n => n > 0).ToList();

    return CivilExecution.WriteAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      var deleted = new List<uint>();
      foreach (var pointNumber in pointNumbers)
      {
        var point = FindPointByNumber(civilDoc, transaction, pointNumber, Autodesk.AutoCAD.DatabaseServices.OpenMode.ForWrite);
        point.Erase();
        deleted.Add(pointNumber);
      }

      return new Dictionary<string, object?>
      {
        ["deleted"] = deleted.Count,
        ["pointNumbers"] = deleted,
      };
    });
  }

  public static Task<object?> ListPointGroupsAsync()
  {
    return CivilExecution.ReadAsync<object?>((doc, civilDoc, database, transaction) =>
    {
      var groups = new List<Dictionary<string, object?>>();
      foreach (Autodesk.AutoCAD.DatabaseServices.ObjectId objectId in civilDoc.PointGroups)
      {
        var group = CivilObjectUtils.GetRequiredObject<PointGroup>(transaction, objectId, Autodesk.AutoCAD.DatabaseServices.OpenMode.ForRead);
        var query = group.GetQuery() as StandardPointGroupQuery;
        groups.Add(new Dictionary<string, object?>
        {
          ["name"] = group.Name,
          ["description"] = group.Description,
          ["pointCount"] = group.PointsCount,
          ["includePattern"] = query?.IncludeNumbers,
          ["excludePattern"] = query?.ExcludeNumbers,
        });
      }

      return new Dictionary<string, object?>
      {
        ["groups"] = groups,
      };
    });
  }

  // "1-500,600,700-710" -> list of inclusive ranges. Null when no filter given.
  internal static List<(uint lo, uint hi)>? ParseNumberRanges(string? spec)
  {
    if (string.IsNullOrWhiteSpace(spec))
    {
      return null;
    }

    var ranges = new List<(uint lo, uint hi)>();
    foreach (var rawPart in spec!.Split(','))
    {
      var part = rawPart.Trim();
      if (part.Length == 0)
      {
        continue;
      }

      var dash = part.IndexOf('-');
      if (dash > 0)
      {
        if (!uint.TryParse(part.Substring(0, dash).Trim(), out var lo) || !uint.TryParse(part.Substring(dash + 1).Trim(), out var hi))
        {
          throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Invalid point number range '{part}'. Use forms like '1-500,600'.");
        }
        ranges.Add(lo <= hi ? (lo, hi) : (hi, lo));
      }
      else
      {
        if (!uint.TryParse(part, out var single))
        {
          throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Invalid point number '{part}'. Use forms like '1-500,600'.");
        }
        ranges.Add((single, single));
      }
    }

    return ranges.Count == 0 ? null : ranges;
  }

  private static bool InRanges(List<(uint lo, uint hi)> ranges, uint number)
  {
    foreach (var (lo, hi) in ranges)
    {
      if (number >= lo && number <= hi)
      {
        return true;
      }
    }
    return false;
  }

  // "TC*,*LO" -> case-insensitive wildcard regexes against the raw description.
  internal static List<System.Text.RegularExpressions.Regex>? ParseWildcardPatterns(string? spec)
  {
    if (string.IsNullOrWhiteSpace(spec))
    {
      return null;
    }

    var patterns = spec!.Split(',')
      .Select(p => p.Trim())
      .Where(p => p.Length > 0)
      .Select(p => new System.Text.RegularExpressions.Regex(
        "^" + System.Text.RegularExpressions.Regex.Escape(p).Replace("\\*", ".*").Replace("\\?", ".") + "$",
        System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant))
      .ToList();

    return patterns.Count == 0 ? null : patterns;
  }

  private static HashSet<string>? ParseLayerSet(JsonArray? layers)
  {
    if (layers == null || layers.Count == 0)
    {
      return null;
    }

    var set = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    foreach (var node in layers)
    {
      var name = node?.GetValue<string>();
      if (!string.IsNullOrWhiteSpace(name))
      {
        set.Add(name!.Trim());
      }
    }
    return set.Count == 0 ? null : set;
  }

  private static (double minX, double minY, double maxX, double maxY)? ParseWindow(JsonObject? window)
  {
    if (window == null)
    {
      return null;
    }

    double Read(string key) => window[key]?.GetValue<double>()
      ?? throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"window is missing '{key}'.");

    var minX = Read("minX");
    var minY = Read("minY");
    var maxX = Read("maxX");
    var maxY = Read("maxY");
    return (Math.Min(minX, maxX), Math.Min(minY, maxY), Math.Max(minX, maxX), Math.Max(minY, maxY));
  }

  private static IEnumerable<CogoPoint> EnumeratePoints(Autodesk.Civil.ApplicationServices.CivilDocument civilDoc, Autodesk.AutoCAD.DatabaseServices.Transaction transaction)
  {
    foreach (Autodesk.AutoCAD.DatabaseServices.ObjectId objectId in civilDoc.CogoPoints)
    {
      yield return CivilObjectUtils.GetRequiredObject<CogoPoint>(transaction, objectId, Autodesk.AutoCAD.DatabaseServices.OpenMode.ForRead);
    }
  }

  private static CogoPoint FindPointByNumber(Autodesk.Civil.ApplicationServices.CivilDocument civilDoc, Autodesk.AutoCAD.DatabaseServices.Transaction transaction, uint pointNumber, Autodesk.AutoCAD.DatabaseServices.OpenMode openMode)
  {
    foreach (Autodesk.AutoCAD.DatabaseServices.ObjectId objectId in civilDoc.CogoPoints)
    {
      var point = CivilObjectUtils.GetRequiredObject<CogoPoint>(transaction, objectId, openMode);
      if (point.PointNumber == pointNumber)
      {
        return point;
      }
    }

    throw new JsonRpcDispatchException("CIVIL3D.OBJECT_NOT_FOUND", $"COGO point '{pointNumber}' was not found.");
  }

  private static HashSet<uint>? TryGetPointNumbersForGroup(Autodesk.Civil.ApplicationServices.CivilDocument civilDoc, Autodesk.AutoCAD.DatabaseServices.Transaction transaction, string groupName)
  {
    foreach (Autodesk.AutoCAD.DatabaseServices.ObjectId objectId in civilDoc.PointGroups)
    {
      var group = CivilObjectUtils.GetRequiredObject<PointGroup>(transaction, objectId, Autodesk.AutoCAD.DatabaseServices.OpenMode.ForRead);
      if (!string.Equals(group.Name, groupName, StringComparison.OrdinalIgnoreCase))
      {
        continue;
      }

      return new HashSet<uint>(group.GetPointNumbers());
    }

    throw new JsonRpcDispatchException("CIVIL3D.OBJECT_NOT_FOUND", $"Point group '{groupName}' was not found.");
  }

  private static IEnumerable<(double X, double Y, double Z, string Description)> ParsePointImport(string data, string format)
  {
    foreach (var rawLine in data.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
    {
      var line = rawLine.Trim();
      if (line.Length == 0)
      {
        continue;
      }

      var tokens = line.Split(new[] { ',', ';', '\t', ' ' }, StringSplitOptions.RemoveEmptyEntries);
      yield return format switch
      {
        "pnezd" when tokens.Length >= 5 => (double.Parse(tokens[1]), double.Parse(tokens[2]), double.Parse(tokens[3]), tokens[4]),
        "penz" when tokens.Length >= 5 => (double.Parse(tokens[1]), double.Parse(tokens[3]), double.Parse(tokens[2]), tokens[4]),
        "xyzd" when tokens.Length >= 4 => (double.Parse(tokens[0]), double.Parse(tokens[1]), double.Parse(tokens[2]), tokens[3]),
        "xyz" when tokens.Length >= 3 => (double.Parse(tokens[0]), double.Parse(tokens[1]), double.Parse(tokens[2]), string.Empty),
        _ => throw new JsonRpcDispatchException("CIVIL3D.INVALID_INPUT", $"Unsupported point import line for format '{format}': {line}"),
      };
    }
  }
}
